# Chat Interface — Production-Ready

A provider-agnostic chat UI with a **FastAPI async backend** and a **Chainlit frontend mounted into FastAPI**. Supports Azure OpenAI, OpenAI, and any OpenAI-compatible endpoint.

## Architecture

```
Chainlit (mounted at /)  ──HTTP──►  FastAPI (backend)  ──HTTPS──►  Azure OpenAI / OpenAI
                                 ├─ Connection pooling (100 conns)
                                 ├─ Rate limiting (100 RPS, burst 150)
                                 ├─ Retry with exponential backoff
                                 ├─ Structured logging (JSON / text)
                                 └─ Health checks (/api/v1/health)
```

## Quick Start

```bash
# 1. Configure
cp .env.example .env   # then edit .env with your values

# 2. Run (auto-creates .venv, installs deps, starts backend + Chainlit UI)
python run.py
```

> **Note:** `run.py` automatically creates a `.venv` virtual environment and
> installs all dependencies into it on first run. Nothing is installed globally.
> You can also run `python setup.py` to set up the venv separately.

- **Chat UI**  → http://localhost:8000
- **Health**   → http://localhost:8000/api/v1/health
- **API Docs** → http://localhost:8000/docs

## Configuration

All settings via `.env` (or environment variables):

### Endpoint
| Variable | Description | Default |
|---|---|---|
| `TARGET_URI` | Full chat-completions URL | — |
| `API_KEY` | API key | — |
| `AZURE_DEPLOYMENT` | Deployment name (Responses API only) | — |

### Server
| Variable | Description | Default |
|---|---|---|
| `BACKEND_PORT` | Backend port (Chainlit UI mounted here) | `8000` |
| `BACKEND_HOST` | Backend bind address | `127.0.0.1` |
| `WORKERS` | Uvicorn worker processes | `4` |

### Networking
| Variable | Description | Default |
|---|---|---|
| `VERIFY_SSL` | Verify SSL certificates | `true` |
| `POOL_SIZE` | Max outbound connections | `100` |
| `CONNECT_TIMEOUT` | TCP connect timeout (s) | `5.0` |
| `READ_TIMEOUT` | HTTP read timeout (s) | `60.0` |
| `WRITE_TIMEOUT` | HTTP write timeout (s) | `10.0` |

### Rate Limiting
| Variable | Description | Default |
|---|---|---|
| `RATE_LIMIT_RPS` | Requests per second | `100` |
| `RATE_LIMIT_BURST` | Max burst size | `150` |

### Retry
| Variable | Description | Default |
|---|---|---|
| `MAX_RETRIES` | Max retries for transient errors | `3` |
| `RETRY_BACKOFF_BASE` | Backoff base delay (s) | `0.5` |

### Logging
| Variable | Description | Default |
|---|---|---|
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | `INFO` |
| `LOG_FORMAT` | `json` (production) / `text` (development) | `json` |

## API Endpoints

### `POST /api/v1/chat`
Send a chat completion request.

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "temperature": 0.7,
  "max_tokens": 512,
  "model": null
}
```

### `GET /api/v1/health`
Liveness/readiness check — returns uptime and pool status.

## Project Structure

```
chat-interface/
├── config.py              # Centralized Pydantic settings
├── logging_config.py      # Structured logging setup
├── run.py                 # Launcher (backend with Chainlit UI)
├── setup.py               # Standalone venv + dependency bootstrap
├── chainlit_app.py        # Chainlit UI (mounted into FastAPI)
├── .chainlit/
│   └── config.toml        # Chainlit configuration
├── public/
│   ├── custom.css         # Custom styling
│   └── *.svg              # Icon assets
├── backend/
│   ├── __init__.py
│   ├── main.py            # FastAPI app with lifespan + Chainlit mount
│   ├── routes.py          # API routes
│   ├── schemas.py         # Pydantic models
│   ├── service.py         # Async chat service + connection pool
│   ├── rate_limiter.py    # Token-bucket rate limiter
│   └── middleware.py      # Request ID, logging, error handling
└── tests/
    ├── __init__.py
    ├── test_service.py
    └── test_routes.py
```

