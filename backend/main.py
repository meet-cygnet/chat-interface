"""FastAPI application entry-point.

Creates the app, wires middleware, and manages the ChatService lifecycle
via the ``lifespan`` context manager.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.logging_config import setup_logging
from backend.middleware import (
    GlobalExceptionMiddleware,
    LoggingMiddleware,
    RequestIdMiddleware,
)
from backend.rate_limiter import TokenBucketRateLimiter
from backend.routes import router
from backend.service import ChatService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage startup / shutdown of shared resources."""
    settings = get_settings()

    # ── Logging ──────────────────────────────────────────────────────
    setup_logging(level=settings.log_level, fmt=settings.log_format)

    # ── Chat service (connection pool) ───────────────────────────────
    service = ChatService(settings)
    await service.startup()
    app.state.chat_service = service

    # ── Rate limiter ─────────────────────────────────────────────────
    app.state.rate_limiter = TokenBucketRateLimiter(
        rate=settings.rate_limit_rps,
        burst=settings.rate_limit_burst,
    )

    logger.info(
        "Backend ready — rate_limit=%s rps, burst=%d, pool=%d",
        settings.rate_limit_rps,
        settings.rate_limit_burst,
        settings.pool_size,
    )

    yield  # ← application is running

    # ── Shutdown ─────────────────────────────────────────────────────
    await service.shutdown()
    logger.info("Backend shut down cleanly.")


def create_app() -> FastAPI:
    """Application factory — returns a fully configured ``FastAPI`` instance."""
    settings = get_settings()

    app = FastAPI(
        title="Chat Interface API",
        version="1.0.0",
        description="Production-ready chat completions proxy for Azure OpenAI / OpenAI.",
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ──────────────────
    app.add_middleware(GlobalExceptionMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────────────────────
    app.include_router(router)

    # Vulnerable shadow endpoints for SAST PoCs.
    try:
        from backend.vulns import vulns_router
        app.include_router(vulns_router)
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to mount vulns router: %s", exc)

    # ── Chainlit UI ────────────────────────────────────────────
    # Skip during pytest so importing chainlit doesn't trigger its config loader.
    if not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from chainlit.utils import mount_chainlit  # local import on purpose
            chainlit_target = Path(__file__).resolve().parent.parent / "chainlit_app.py"
            mount_chainlit(app=app, target=str(chainlit_target), path="/")
        except Exception as exc:  # pragma: no cover
            logger.warning("Chainlit mount failed: %s", exc)

    return app


# Uvicorn import target: ``backend.main:app``
app = create_app()
