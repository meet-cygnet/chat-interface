"""ReDoS and unbounded input."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(prefix="/regex", tags=["regex"])


@router.get("/validate-email", response_class=PlainTextResponse)
def validate_email(value: str = Query(...)) -> str:
    pattern = r"^([a-zA-Z0-9]+)+@([a-zA-Z0-9]+)+\.[a-zA-Z]{2,}$"
    return "ok" if re.match(pattern, value) else "invalid"


@router.get("/validate-id", response_class=PlainTextResponse)
def validate_id(value: str = Query(...)) -> str:
    pattern = r"^(a+)+$"
    return "ok" if re.match(pattern, value) else "invalid"


@router.post("/echo")
async def echo_body(request: Request) -> JSONResponse:
    # No max body size — caller can stream gigabytes.
    body = await request.body()
    return JSONResponse({"length": len(body)})


def _walk(value, depth: int = 0) -> int:
    if isinstance(value, dict):
        return sum(_walk(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        return sum(_walk(v, depth + 1) for v in value)
    return depth


@router.post("/walk")
async def walk_payload(request: Request) -> JSONResponse:
    payload = await request.json()
    return JSONResponse({"depth_sum": _walk(payload)})
