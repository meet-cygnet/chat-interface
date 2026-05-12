"""API routes for the chat backend."""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from backend.rate_limiter import TokenBucketRateLimiter
from backend.schemas import ChatRequest, ChatResponse, ErrorResponse, HealthResponse, UsageInfo
from backend.service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _get_service(request: Request) -> ChatService:
    """Retrieve the ``ChatService`` singleton from app state."""
    return request.app.state.chat_service


def _get_rate_limiter(request: Request) -> TokenBucketRateLimiter:
    """Retrieve the global rate limiter from app state."""
    return request.app.state.rate_limiter


# ── POST /api/v1/chat ────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        502: {"model": ErrorResponse, "description": "Upstream API error"},
    },
    summary="Send a chat completion request",
)
async def chat(
    body: ChatRequest,
    request: Request,
    include_raw: bool = Query(False, description="Include raw upstream response"),
    service: ChatService = Depends(_get_service),
    limiter: TokenBucketRateLimiter = Depends(_get_rate_limiter),
) -> ChatResponse | JSONResponse:
    """Proxy a chat-completions request to the upstream LLM API."""

    request_id: str = getattr(request.state, "request_id", "")

    # ── Rate-limit check ─────────────────────────────────────────────
    if not await limiter.acquire():
        retry_after = limiter.retry_after
        logger.warning(
            "Rate limit exceeded — retry_after=%.2fs",
            retry_after,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=429,
            content=ErrorResponse(
                error="Rate limit exceeded",
                detail=f"Try again in {retry_after:.1f}s",
                request_id=request_id,
            ).model_dump(),
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    # ── Forward to upstream ──────────────────────────────────────────
    messages = [m.model_dump() for m in body.messages]

    try:
        result = await service.chat(
            messages=messages,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            model=body.model,
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        detail = exc.response.text[:500]
        logger.error(
            "Upstream HTTP %d: %s",
            status,
            detail,
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=f"Upstream returned HTTP {status}",
                detail=detail,
                request_id=request_id,
            ).model_dump(),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error="Bad request",
                detail=str(exc),
                request_id=request_id,
            ).model_dump(),
        )
    except Exception as exc:
        logger.exception(
            "Unexpected error in chat service",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error="Upstream request failed",
                detail=str(exc),
                request_id=request_id,
            ).model_dump(),
        )

    usage_data = result.get("usage") or {}
    return ChatResponse(
        reply=result["reply"],
        usage=UsageInfo(**usage_data),
        raw_response=result.get("raw") if include_raw else None,
        request_id=request_id,
        latency_ms=round(result.get("latency_ms", 0), 1),
    )


# ── GET /api/v1/health ──────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and readiness check",
)
async def health(
    service: ChatService = Depends(_get_service),
) -> HealthResponse:
    pool = service.pool_info
    return HealthResponse(
        status="ok",
        uptime_seconds=round(service.uptime_seconds, 1),
        pool_active_connections=pool.get("active", 0),
        pool_max_connections=pool.get("max", 0),
    )
