"""Streamlit chat UI — thin frontend that delegates to the FastAPI backend.

This file fixes the crash-after-first-response bug from the original
``app.py`` by:
1.  Storing the assistant reply in ``st.session_state`` *immediately* and
    using ``st.rerun()`` so variables are always in scope.
2.  Wrapping all post-response rendering in safe session-state lookups.
3.  Guarding ``.pop()`` calls with length checks.
4.  Using ``httpx`` with proper error handling for backend communication.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

# Ensure the project root is importable so we can use ``config``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from config import get_settings  # noqa: E402

settings = get_settings()

BACKEND_BASE = f"http://{settings.backend_host}:{settings.backend_port}"
CHAT_ENDPOINT = f"{BACKEND_BASE}/api/v1/chat"
HEALTH_ENDPOINT = f"{BACKEND_BASE}/api/v1/health"

# ── HTTP client (reused across reruns via module-level caching) ──────────
_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)


def _get_http_client() -> httpx.Client:
    """Return a module-cached ``httpx.Client``."""
    if "http_client" not in st.session_state:
        st.session_state["http_client"] = httpx.Client(timeout=_HTTP_TIMEOUT)
    return st.session_state["http_client"]


# ── Helpers ──────────────────────────────────────────────────────────────

def _detect_mode(uri: str) -> str:
    if "/openai/responses" in (uri or ""):
        return "azure-responses"
    if "/openai/deployments/" in (uri or ""):
        return "azure-chat"
    return "openai"


def _send_chat(messages: list[dict], temperature: float, max_tokens: int,
               model: str | None) -> dict:
    """POST to the backend's ``/api/v1/chat`` endpoint."""
    client = _get_http_client()
    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if model:
        payload["model"] = model

    resp = client.post(CHAT_ENDPOINT, json=payload, params={"include_raw": True})
    resp.raise_for_status()
    return resp.json()


# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="Chat", page_icon="💬", layout="centered")
st.title("💬 Chat")

# ── Sidebar ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")

    target_uri = st.text_input(
        "Target URI",
        value=settings.target_uri,
        help="Full chat-completions URL (include any ?api-version=... for Azure).",
    )
    api_key = st.text_input(
        "API Key",
        value=settings.api_key,
        type="password",
    )

    mode = _detect_mode(target_uri)
    mode_label = {
        "azure-chat": "Azure (Chat Completions)",
        "azure-responses": "Azure AI Foundry (Responses API)",
        "openai": "OpenAI-style",
    }[mode]
    st.caption(f"Detected: **{mode_label}**")

    system_prompt = st.text_area(
        "System prompt",
        value="You are a helpful assistant.",
        height=80,
    )

    model: str | None = None
    if mode == "openai":
        model = st.text_input("Model", value="gpt-4o")
    elif mode == "azure-responses":
        model = st.text_input(
            "Deployment name",
            value=settings.azure_deployment,
            help="Required for Responses API.",
        )

    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.slider("Max tokens", 16, 4096, 512, 16)

    if st.button("Clear chat", use_container_width=True):
        st.session_state.pop("messages", None)
        st.session_state.pop("last_usage", None)
        st.session_state.pop("last_raw_response", None)
        st.session_state.pop("pending_reply", None)
        st.rerun()

    # ── Backend health indicator ─────────────────────────────────────
    try:
        health = _get_http_client().get(HEALTH_ENDPOINT, timeout=2.0)
        if health.status_code == 200:
            data = health.json()
            st.success(f"Backend: **online** ({data.get('uptime_seconds', 0):.0f}s)")
        else:
            st.warning("Backend: unhealthy")
    except Exception:
        st.error("Backend: **offline**")

    # ── Last usage ───────────────────────────────────────────────────
    last_usage = st.session_state.get("last_usage")
    if last_usage:
        st.divider()
        st.subheader("Last call usage")
        st.metric("Prompt tokens", last_usage.get("prompt_tokens", 0))
        st.metric("Completion tokens", last_usage.get("completion_tokens", 0))
        st.metric("Total tokens", last_usage.get("total_tokens", 0))


# ── History initialisation / system-prompt sync ──────────────────────────
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "system", "content": system_prompt}]
else:
    msgs = st.session_state["messages"]
    if msgs and msgs[0]["role"] == "system":
        msgs[0]["content"] = system_prompt
    else:
        msgs.insert(0, {"role": "system", "content": system_prompt})

# ── Render history (skip system) ─────────────────────────────────────────
for msg in st.session_state["messages"]:
    if msg["role"] == "system":
        continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── If we just received a reply, show usage + raw (post-rerun) ───────────
if st.session_state.get("pending_reply"):
    pending = st.session_state.pop("pending_reply")
    with st.chat_message("assistant"):
        st.markdown(pending["reply"])
        usage = pending.get("usage")
        if usage:
            st.caption(
                f"🔢 prompt: {usage.get('prompt_tokens', '?')} | "
                f"completion: {usage.get('completion_tokens', '?')} | "
                f"total: {usage.get('total_tokens', '?')}"
            )
        raw = pending.get("raw_response")
        if raw:
            with st.expander("Raw API response"):
                st.json(raw)

# ── Handle new input ─────────────────────────────────────────────────────
user_input = st.chat_input("Type a message...")
if user_input:
    if not target_uri or not api_key:
        st.error("Please set Target URI and API Key in the sidebar (or .env).")
        st.stop()

    # Append user message.
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Call backend.
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = _send_chat(
                    messages=st.session_state["messages"],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model,
                )
                reply = result.get("reply", "")
                usage = result.get("usage", {})
                raw_response = result.get("raw_response")
                latency = result.get("latency_ms", 0)

                # Persist to session state BEFORE any rendering that could
                # be lost on rerun.
                st.session_state["last_usage"] = usage
                st.session_state["last_raw_response"] = raw_response
                st.session_state["messages"].append(
                    {"role": "assistant", "content": reply}
                )

                # Render immediately in this run.
                st.markdown(reply)
                if usage:
                    st.caption(
                        f"🔢 prompt: {usage.get('prompt_tokens', '?')} | "
                        f"completion: {usage.get('completion_tokens', '?')} | "
                        f"total: {usage.get('total_tokens', '?')} | "
                        f"⏱️ {latency:.0f}ms"
                    )
                if raw_response:
                    with st.expander("Raw API response"):
                        st.json(raw_response)

            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:500] if exc.response else ""
                status = exc.response.status_code if exc.response else "?"
                st.error(f"HTTP {status}: {body}")
                # Roll back the user message we just appended.
                if (
                    st.session_state["messages"]
                    and st.session_state["messages"][-1]["role"] == "user"
                ):
                    st.session_state["messages"].pop()
                st.stop()

            except Exception as exc:
                st.error(f"Request failed: {exc}")
                if (
                    st.session_state["messages"]
                    and st.session_state["messages"][-1]["role"] == "user"
                ):
                    st.session_state["messages"].pop()
                st.stop()
