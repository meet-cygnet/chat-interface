"""Centralized configuration with Pydantic validation.

All settings are loaded from environment variables (with .env fallback).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load .env from the project root (one level up from this file).
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH, override=False)


class Settings(BaseSettings):
    """Application-wide settings — every value can be overridden via env vars."""

    # ── Azure / OpenAI endpoint ──────────────────────────────────────────
    target_uri: str = Field(
        default="",
        description="Full chat-completions URL. Include ?api-version=... for Azure.",
    )
    api_key: str = Field(
        default="",
        description="API key for the target endpoint.",
    )
    azure_deployment: str = Field(
        default="",
        description="Deployment name (required only for Azure Responses API).",
    )

    # ── Networking ───────────────────────────────────────────────────────
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates on outbound requests.",
    )
    connect_timeout: float = Field(
        default=5.0,
        description="TCP connect timeout in seconds.",
    )
    read_timeout: float = Field(
        default=60.0,
        description="HTTP read timeout in seconds.",
    )
    write_timeout: float = Field(
        default=10.0,
        description="HTTP write timeout in seconds.",
    )
    pool_size: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Max connections in the HTTP connection pool.",
    )

    # ── Retry policy ─────────────────────────────────────────────────────
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Max retries for transient HTTP errors.",
    )
    retry_backoff_base: float = Field(
        default=0.5,
        description="Base delay (seconds) for exponential backoff.",
    )

    # ── Rate limiting ────────────────────────────────────────────────────
    rate_limit_rps: float = Field(
        default=100.0,
        gt=0,
        description="Global rate limit in requests per second.",
    )
    rate_limit_burst: int = Field(
        default=150,
        ge=1,
        description="Max burst size for the token bucket.",
    )

    # ── Server ───────────────────────────────────────────────────────────
    backend_host: str = Field(default="127.0.0.1")
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_port: int = Field(default=8501, ge=1, le=65535)
    workers: int = Field(
        default=4,
        ge=1,
        le=32,
        description="Number of uvicorn worker processes.",
    )

    # ── Logging ──────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="json",
        description="Log output format: 'json' or 'text'.",
    )

    # ── Model config ─────────────────────────────────────────────────────
    model_config = {
        "env_file": str(_ENV_PATH),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    # Map legacy env var PORT → frontend_port
    @field_validator("frontend_port", mode="before")
    @classmethod
    def _port_alias(cls, v: int | str | None) -> int:
        """Allow the legacy ``PORT`` env var to set ``frontend_port``."""
        port_env = os.getenv("PORT")
        if v in (None, 8501, "8501") and port_env:
            return int(port_env)
        return int(v) if v is not None else 8501

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        return v.upper().strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance."""
    return Settings()
