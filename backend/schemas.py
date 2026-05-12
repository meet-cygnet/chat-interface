"""Pydantic request / response schemas for the chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single message in the conversation."""

    role: str = Field(..., pattern=r"^(system|user|assistant)$")
    content: str = Field(..., min_length=1, max_length=100_000)


class ChatRequest(BaseModel):
    """Body of ``POST /api/v1/chat``."""

    messages: list[ChatMessage] = Field(..., min_length=1, max_length=200)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=1, le=128_000)
    model: str | None = Field(
        default=None,
        description="Model / deployment name. Required for OpenAI-style and Azure Responses API.",
    )


# ── Response ─────────────────────────────────────────────────────────────

class UsageInfo(BaseModel):
    """Token usage statistics."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Successful response from ``POST /api/v1/chat``."""

    reply: str
    usage: UsageInfo = Field(default_factory=UsageInfo)
    raw_response: dict | None = Field(
        default=None,
        description="Raw upstream API response (only when include_raw=true).",
    )
    request_id: str = ""
    latency_ms: float = 0.0


class HealthResponse(BaseModel):
    """Response from ``GET /api/v1/health``."""

    status: str = "ok"
    uptime_seconds: float = 0.0
    pool_active_connections: int = 0
    pool_max_connections: int = 0


class ErrorResponse(BaseModel):
    """Structured error body."""

    error: str
    detail: str = ""
    request_id: str = ""
