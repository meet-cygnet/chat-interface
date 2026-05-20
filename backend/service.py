"""Async chat service with connection pooling and retry logic.

This is the core business logic layer — it manages an ``httpx.AsyncClient``
connection pool and handles Azure / OpenAI endpoint detection, payload
formatting, response parsing, and transient-error retries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# HTTP status codes that are safe to retry (transient).
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# ── Endpoint detection ───────────────────────────────────────────────────

def detect_mode(uri: str) -> str:
    """Return ``'azure-chat'``, ``'azure-responses'``, or ``'openai'``."""
    if "/openai/responses" in (uri or "") or "/openai/v1/responses" in (uri or "") or (uri or "").endswith("/responses"):
        return "azure-responses"
    if "/openai/deployments/" in (uri or "") or ("services.ai.azure.com" in (uri or "") and "/openai/v1" in (uri or "")):
        return "azure-chat"
    return "openai"


# ── Response parsing ─────────────────────────────────────────────────────

def parse_response(mode: str, data: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """Extract ``(reply_text, usage_dict)`` from the upstream API response."""
    if mode == "azure-responses":
        reply = data.get("output_text")
        if not reply:
            chunks: list[str] = []
            for item in data.get("output") or []:
                for c in item.get("content") or []:
                    t = c.get("text")
                    if isinstance(t, str):
                        chunks.append(t)
                    elif isinstance(t, dict) and "value" in t:
                        chunks.append(t["value"])
            reply = "".join(chunks)
        raw_usage = data.get("usage") or {}
        usage = {
            "prompt_tokens": raw_usage.get("input_tokens", 0),
            "completion_tokens": raw_usage.get("output_tokens", 0),
            "total_tokens": raw_usage.get("total_tokens", 0),
        }
        return reply or "", usage

    # Chat-completions shape (Azure Chat / OpenAI).
    choices = data.get("choices")
    if not choices:
        raise ValueError("Upstream response missing 'choices' field.")
    reply = choices[0].get("message", {}).get("content", "")
    return reply, data.get("usage") or {}


# ── Service class ────────────────────────────────────────────────────────

class ChatService:
    """Manages outbound HTTP calls to the upstream LLM API.

    * Maintains a persistent ``httpx.AsyncClient`` connection pool.
    * Retries transient errors with exponential back-off.
    * Thread-safe for use across concurrent FastAPI requests.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None
        self._started_at: float = time.monotonic()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Create the connection pool.  Call once at application startup."""
        limits = httpx.Limits(
            max_connections=self._settings.pool_size,
            max_keepalive_connections=self._settings.pool_size,
            keepalive_expiry=30,
        )
        timeout = httpx.Timeout(
            connect=self._settings.connect_timeout,
            read=self._settings.read_timeout,
            write=self._settings.write_timeout,
            pool=10.0,
        )
        self._client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            verify=self._settings.verify_ssl,
            http2=True,
        )
        logger.info(
            "ChatService started — pool_size=%d, verify_ssl=%s",
            self._settings.pool_size,
            self._settings.verify_ssl,
        )

    async def shutdown(self) -> None:
        """Drain and close the connection pool.  Call at application shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("ChatService shut down — connection pool closed.")

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def pool_info(self) -> dict[str, int]:
        """Return basic pool metrics for the health endpoint."""
        if self._client is None:
            return {"active": 0, "max": 0}
        pool = self._client._transport  # type: ignore[attr-defined]
        # httpx uses httpcore underneath; introspect safely.
        try:
            info = pool._pool  # type: ignore[attr-defined]
            return {
                "active": len([c for c in info._connections if c.is_idle() is False]),
                "max": self._settings.pool_size,
            }
        except Exception:
            return {"active": 0, "max": self._settings.pool_size}

    # ── Core request ─────────────────────────────────────────────────

    async def chat(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        model: str | None = None,
        target_uri: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Send a chat request and return ``{"reply": ..., "usage": ..., "raw": ...}``."""
        if self._client is None:
            raise RuntimeError("ChatService not started — call startup() first.")

        uri = target_uri or self._settings.target_uri
        key = api_key or self._settings.api_key
        if not uri or not key:
            raise ValueError("target_uri and api_key are required.")

        mode = detect_mode(uri)
        headers = self._build_headers(mode, key)
        resolved_model = model or (self._settings.azure_deployment if self._settings.azure_deployment else None)
        payload = self._build_payload(mode, messages, temperature, max_tokens, resolved_model)

        start = time.monotonic()
        data = await self._post_with_retry(uri, headers, payload)
        elapsed_ms = (time.monotonic() - start) * 1000

        reply, usage = parse_response(mode, data)

        logger.info(
            "Chat completed in %.1fms — tokens=%s",
            elapsed_ms,
            usage.get("total_tokens", "?"),
        )
        return {"reply": reply, "usage": usage, "raw": data, "latency_ms": elapsed_ms}

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_headers(mode: str, key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if mode in ("azure-chat", "azure-responses"):
            headers["api-key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    @staticmethod
    def _build_payload(
        mode: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        model: str | None,
    ) -> dict[str, Any]:
        if mode == "azure-responses":
            if not model:
                raise ValueError(
                    "Azure Responses API requires a deployment name in 'model'."
                )
            # Responses API accepts either a string input or message array
            # For single user message, use string; for multi-turn, use message array
            if len(messages) == 1 and messages[0].get("role") == "user":
                # Simple single-turn conversation - use string input
                return {
                    "model": model,
                    "input": messages[0].get("content", ""),
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
            else:
                # Multi-turn conversation - use message array with type field
                transformed_input = []
                for msg in messages:
                    transformed_input.append({
                        "type": "message",
                        "role": msg.get("role"),
                        "content": msg.get("content")
                    })
                return {
                    "model": model,
                    "input": transformed_input,
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                }
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if mode == "openai" and model:
            payload["model"] = model
        return payload

    async def _post_with_retry(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST with exponential back-off for transient errors."""
        assert self._client is not None

        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                resp = await self._client.post(url, headers=headers, json=payload)

                if resp.status_code in _RETRYABLE_STATUS_CODES and attempt < self._settings.max_retries:
                    delay = self._settings.retry_backoff_base * (2 ** attempt)
                    # Respect Retry-After header if present.
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    logger.warning(
                        "Retryable HTTP %d on attempt %d/%d — retrying in %.1fs",
                        resp.status_code,
                        attempt + 1,
                        self._settings.max_retries + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                resp.raise_for_status()
                return resp.json()

            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._settings.max_retries:
                    delay = self._settings.retry_backoff_base * (2 ** attempt)
                    logger.warning(
                        "Network error on attempt %d/%d: %s — retrying in %.1fs",
                        attempt + 1,
                        self._settings.max_retries + 1,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

        # Should not reach here, but just in case:
        raise last_exc or RuntimeError("Exhausted retries with no response.")
