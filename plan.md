# Replace Streamlit Frontend with a Modern, Visually Appealing Chat UI

## Background

The current Streamlit frontend (`frontend/app.py`) is functional but visually basic — it uses Streamlit's default widgets and styling. The goal is to replace it with a stunning, modern chat interface while keeping the existing FastAPI backend intact.

## Options Evaluated

| Option | Visual Appeal | Integration Effort | Customizability |
|---|---|---|---|
| **Chainlit** (mount into FastAPI) | ⭐⭐⭐⭐ — polished dark/light, modern React UI | Low — `pip install chainlit`, mount via `mount_chainlit()` | Moderate — themes, custom CSS/JS, logos |
| **Gradio** | ⭐⭐ — rigid, demo-like | Low | Low |
| **Custom HTML/CSS/JS** | ⭐⭐⭐⭐⭐ — full control | High — build from scratch | Unlimited |

## Recommended: Chainlit

> [!IMPORTANT]
> **Chainlit** provides the best balance: it's a purpose-built, beautiful chat UI with dark mode, streaming support, token usage display, and it mounts directly into your existing FastAPI app. No need to run a separate frontend process.

### Key benefits
- **Dark/light mode** out of the box with modern Shadcn-based theming
- **Streaming** support built-in (real-time token-by-token responses)
- **Chat history**, conversation management, chain-of-thought visualization
- **Custom branding** (logos, favicons, CSS overrides)
- **Mounts into your existing FastAPI** — single process, single port
- **Chat starters** — pre-built prompt buttons for quick onboarding
- **Token usage** displayed natively

## Proposed Changes

### Backend Integration

#### [MODIFY] [main.py](file:///c:/Users/meet.soni/OneDrive%20-%20Cygnet%20Infotech%20Pvt.%20Ltd/Documents/Learning/azure-open-ai/chat-interface/backend/main.py)
- Add `mount_chainlit()` call to mount the Chainlit UI at the root path `/`
- Keep all existing API routes (`/api/v1/chat`, `/api/v1/health`) working as-is

---

### New Chainlit Frontend

#### [NEW] `chainlit_app.py` (project root)
- Implement `@cl.on_chat_start` — welcome message, load settings from config
- Implement `@cl.on_message` — forward user messages to the FastAPI backend's `/api/v1/chat` endpoint using `httpx`
- Display token usage and latency as step metadata
- Add chat starters for common prompts
- Support settings panel for temperature, max_tokens, and model selection

#### [NEW] `public/logo_dark.png` and `public/logo_light.png`
- Generated branding logos for the chat interface

#### [NEW] `.chainlit/config.toml`
- Set default theme to `dark`
- Configure app name, description, and layout
- Set custom CSS path for additional polish

#### [NEW] `public/custom.css`
- Minor CSS overrides for extra visual polish (gradients, font tweaks)

---

### Configuration & Launcher Updates

#### [MODIFY] [requirements.txt](file:///c:/Users/meet.soni/OneDrive%20-%20Cygnet%20Infotech%20Pvt.%20Ltd/Documents/Learning/azure-open-ai/chat-interface/requirements.txt)
- Add `chainlit>=2.0`

#### [MODIFY] [run.py](file:///c:/Users/meet.soni/OneDrive%20-%20Cygnet%20Infotech%20Pvt.%20Ltd/Documents/Learning/azure-open-ai/chat-interface/run.py)
- Remove the Streamlit frontend subprocess launch
- Backend now serves everything (API + Chainlit UI) on a single port (8000)
- Simplify the launcher significantly

#### [MODIFY] [README.md](file:///c:/Users/meet.soni/OneDrive%20-%20Cygnet%20Infotech%20Pvt.%20Ltd/Documents/Learning/azure-open-ai/chat-interface/README.md)
- Update architecture diagram and instructions to reflect Chainlit UI
- Remove Streamlit references, update ports

> [!NOTE]  
> The old `frontend/app.py` (Streamlit) will **not be deleted** — just no longer launched. You can remove it manually when ready.

## Open Questions

1. **Streaming**: Should the new UI stream responses token-by-token, or continue with the current request/response pattern? Chainlit supports both. Streaming would require a small backend change (SSE or WebSocket endpoint).
2. **Authentication**: Do you want to add a login page? Chainlit supports OAuth, header-based, and password-based auth out of the box.

## Verification Plan

### Automated Tests
- Existing `tests/test_service.py` and `tests/test_routes.py` remain unchanged (backend untouched)
- Run `python run.py --test` to verify no regressions

### Manual Verification
- Start with `python run.py`, open `http://localhost:8000` in browser
- Verify: dark mode, chat input, send message, see response, token usage display
- Verify: `/api/v1/health` and `/docs` still accessible
- Record a browser demo of the new UI
