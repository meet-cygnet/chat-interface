from __future__ import annotations

from typing import Any

import chainlit as cl
import httpx
from chainlit.input_widget import Slider, TextInput

from backend.core.config import get_settings

_SYSTEM_PROMPT = "You are a helpful assistant."
_HTTP_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0)


def _backend_base_url() -> str:
    settings = get_settings()
    host = settings.backend_host
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    return f"http://{host}:{settings.backend_port}"


def _detect_mode(uri: str) -> str:
    if "/openai/responses" in (uri or ""):
        return "azure-responses"
    if "/openai/deployments/" in (uri or ""):
        return "azure-chat"
    return "openai"


def _initial_model() -> str:
    settings = get_settings()
    mode = _detect_mode(settings.target_uri)
    if mode == "azure-responses":
        return settings.azure_deployment
    if mode == "openai":
        return "gpt-4o"
    return ""


def _settings_widgets() -> list[Any]:
    return [
        Slider(
            id="temperature",
            label="Temperature",
            initial=0.7,
            min=0,
            max=2,
            step=0.1,
        ),
        Slider(
            id="max_tokens",
            label="Max tokens",
            initial=512,
            min=16,
            max=4096,
            step=16,
        ),
        TextInput(
            id="model",
            label="Model / deployment",
            initial=_initial_model(),
            placeholder="Required for OpenAI-style and Azure Responses API",
        ),
    ]


async def _post_chat(payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{_backend_base_url()}/api/v1/chat"
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


@cl.set_starters
async def set_starters() -> list[cl.Starter]:
    return [
        cl.Starter(
            label="Explain a concept",
            message="Explain Azure OpenAI chat completions in simple terms.",
            icon="/public/lightbulb.svg",
        ),
        cl.Starter(
            label="Draft an email",
            message="Draft a concise professional email requesting a project status update.",
            icon="/public/mail.svg",
        ),
        cl.Starter(
            label="Review code",
            message="Review this code for correctness, readability, and edge cases:\n\n",
            icon="/public/code.svg",
        ),
    ]


@cl.on_chat_start
async def on_chat_start() -> None:
    settings = await cl.ChatSettings(_settings_widgets()).send()
    cl.user_session.set("settings", settings)
    cl.user_session.set("messages", [{"role": "system", "content": _SYSTEM_PROMPT}])
    await cl.Message(
        content=(
            "Welcome! I am connected to your FastAPI chat backend. "
            "Use the settings panel to adjust temperature, max tokens, and model."
        )
    ).send()


@cl.on_settings_update
async def on_settings_update(settings: dict[str, Any]) -> None:
    cl.user_session.set("settings", settings)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    history = cl.user_session.get("messages") or [
        {"role": "system", "content": _SYSTEM_PROMPT}
    ]
    settings = cl.user_session.get("settings") or {}

    history.append({"role": "user", "content": message.content})

    payload: dict[str, Any] = {
        "messages": history,
        "temperature": float(settings.get("temperature", 0.7)),
        "max_tokens": int(settings.get("max_tokens", 512)),
    }
    model = str(settings.get("model") or "").strip()
    if model:
        payload["model"] = model

    response_message = cl.Message(content="")
    await response_message.send()

    try:
        result = await _post_chat(payload)
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:500] if exc.response else ""
        response_message.content = f"Backend returned HTTP {exc.response.status_code}: {body}"
        await response_message.update()
        history.pop()
        cl.user_session.set("messages", history)
        return
    except Exception as exc:
        response_message.content = f"Request failed: {exc}"
        await response_message.update()
        history.pop()
        cl.user_session.set("messages", history)
        return

    reply = result.get("reply", "")
    usage = result.get("usage") or {}
    latency_ms = result.get("latency_ms", 0)

    history.append({"role": "assistant", "content": reply})
    cl.user_session.set("messages", history)

    usage_line = (
        f"\n\n---\n"
        f"Prompt tokens: {usage.get('prompt_tokens', 0)} · "
        f"Completion tokens: {usage.get('completion_tokens', 0)} · "
        f"Total tokens: {usage.get('total_tokens', 0)} · "
        f"Latency: {latency_ms:.0f}ms"
    )
    response_message.content = f"{reply}{usage_line}"
    await response_message.update()
