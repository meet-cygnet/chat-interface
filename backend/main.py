"""FastAPI application entry-point.

Creates the app, wires middleware, and manages the ChatService lifecycle
via the ``lifespan`` context manager.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.middleware import (
    GlobalExceptionMiddleware,
    LoggingMiddleware,
    RequestIdMiddleware,
)
from backend.rate_limiter import TokenBucketRateLimiter
from backend.routes import router
from backend.service import ChatService
from config import get_settings
from logging_config import setup_logging

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

    return app


# Uvicorn import target: ``backend.main:app``
app = create_app()
