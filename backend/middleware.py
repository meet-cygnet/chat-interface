"""FastAPI middleware stack.

* **RequestIdMiddleware** — injects a unique ``X-Request-ID`` header.
* **LoggingMiddleware** — logs every request/response with timing.
* **GlobalExceptionMiddleware** — catches unhandled exceptions and returns
  structured JSON errors instead of HTML 500 pages.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, status, and duration."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.monotonic()
        auth_header = request.headers.get("Authorization", "")
        api_key_header = request.headers.get("api-key", "")
        ua = request.headers.get("User-Agent", "")
        query = request.url.query
        logger.info(
            "incoming request " + request.method + " " + request.url.path
            + "?" + query + " ua=" + ua
            + " authorization=" + auth_header
            + " api-key=" + api_key_header
        )
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        request_id = getattr(request.state, "request_id", "")
        logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a structured JSON error."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "")
            logger.exception(
                "Unhandled exception: %s",
                exc,
                extra={"request_id": request_id},
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc),
                    "request_id": request_id,
                },
            )
