"""Generic chat-completions Streamlit UI.

Driven by just two variables: TARGET_URI and API_KEY.
Auto-detects Azure vs OpenAI-style based on URL.
"""
import os

import requests
import streamlit as st
import urllib3
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def is_azure_chat_uri(uri: str) -> bool:
    return "/openai/deployments/" in (uri or "")


def is_azure_responses_uri(uri: str) -> bool:
    return "/openai/responses" in (uri or "")


def is_azure_uri(uri: str) -> bool:
    return is_azure_chat_uri(uri) or is_azure_responses_uri(uri)


def detect_mode(uri: str) -> str:
    """Returns 'azure-chat', 'azure-responses', or 'openai'."""
    if is_azure_responses_uri(uri):
        return "azure-responses"
    if is_azure_chat_uri(uri):
        return "azure-chat"
    return "openai"


def _parse_response(mode: str, data: dict) -> tuple[str, dict]:
    """Extract (reply_text, usage_dict) from API response based on mode."""
    if mode == "azure-responses":
        reply = data.get("output_text")
        if not reply:
            # Walk output[].content[].text
            chunks = []
            for item in data.get("output", []) or []:
                for c in item.get("content", []) or []:
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
    # chat completions shape
    reply = data["choices"][0]["message"]["content"]
    return reply, data.get("usage") or {}


def call_chat_completions(uri: str, key: str, messages: list, temperature: float,
                          max_tokens: int, model: str | None, verify_ssl: bool) -> dict:
    mode = detect_mode(uri)
    headers = {"Content-Type": "application/json"}
    if mode in ("azure-chat", "azure-responses"):
        headers["api-key"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"

    if mode == "azure-responses":
        if not model:
            raise ValueError("Azure Responses API requires a deployment name in 'Model'.")
        payload: dict = {
            "model": model,
            "input": messages,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
    else:
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if mode == "openai" and model:
            payload["model"] = model

    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    resp = requests.post(uri, headers=headers, json=payload, timeout=60, verify=verify_ssl)
    resp.raise_for_status()
    return resp.json()


st.set_page_config(page_title="Chat", page_icon="💬", layout="centered")
st.title("💬 Chat")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")

    target_uri = st.text_input(
        "Target URI",
        value=os.getenv("TARGET_URI", ""),
        help="Full chat-completions URL (include any ?api-version=... for Azure).",
    )
    api_key = st.text_input(
        "API Key",
        value=os.getenv("API_KEY", ""),
        type="password",
    )

    mode = detect_mode(target_uri)
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

    model = None
    if mode == "openai":
        model = st.text_input("Model", value="gpt-4o")
    elif mode == "azure-responses":
        model = st.text_input(
            "Deployment name",
            value=os.getenv("AZURE_DEPLOYMENT", ""),
            help="Required for Responses API. Use the deployment name from Azure AI Foundry.",
        )

    temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
    max_tokens = st.slider("Max tokens", 16, 4096, 512, 16)

    verify_ssl = st.checkbox(
        "Verify SSL certificate",
        value=_env_bool("VERIFY_SSL", True),
        help="Uncheck to bypass SSL verification (insecure; useful behind corporate proxies).",
    )
    if not verify_ssl:
        st.warning("SSL verification disabled.", icon="⚠️")

    if st.button("Clear chat", use_container_width=True):
        st.session_state.pop("messages", None)
        st.session_state.pop("last_usage", None)
        st.session_state.pop("last_response", None)
        st.rerun()

    last_usage = st.session_state.get("last_usage")
    if last_usage:
        st.divider()
        st.subheader("Last call usage")
        st.metric("Prompt tokens", last_usage.get("prompt_tokens", 0))
        st.metric("Completion tokens", last_usage.get("completion_tokens", 0))
        st.metric("Total tokens", last_usage.get("total_tokens", 0))

# --- History init / system prompt sync ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
else:
    # Keep system prompt in sync with sidebar edits.
    if st.session_state.messages and st.session_state.messages[0]["role"] == "system":
        st.session_state.messages[0]["content"] = system_prompt
    else:
        st.session_state.messages.insert(0, {"role": "system", "content": system_prompt})

# --- Render history (skip system) ---
for msg in st.session_state.messages:
    if msg["role"] == "system":
        continue
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Handle new input ---
user_input = st.chat_input("Type a message...")
if user_input:
    if not target_uri or not api_key:
        st.error("Please set Target URI and API Key in the sidebar (or .env).")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        with st.spinner("Thinking..."):
            try:
                data = call_chat_completions(
                    uri=target_uri,
                    key=api_key,
                    messages=st.session_state.messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model,
                    verify_ssl=verify_ssl,
                )
                reply, usage = _parse_response(detect_mode(target_uri), data)
                st.session_state["last_response"] = data
                st.session_state["last_usage"] = usage
            except requests.HTTPError as e:
                body = e.response.text if e.response is not None else ""
                st.error(f"HTTP {e.response.status_code if e.response else '?'}: {body}")
                st.session_state.messages.pop()  # remove the user msg we just added
                st.stop()
            except Exception as e:
                st.error(f"Request failed: {e}")
                st.session_state.messages.pop()
                st.stop()

        placeholder.markdown(reply)
        if usage:
            st.caption(
                f"🔢 prompt: {usage.get('prompt_tokens', '?')} | "
                f"completion: {usage.get('completion_tokens', '?')} | "
                f"total: {usage.get('total_tokens', '?')}"
            )
        with st.expander("Raw API response"):
            st.json(data)
        st.session_state.messages.append({"role": "assistant", "content": reply})
