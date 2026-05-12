"""Information disclosure — env dump, stack traces, server internals."""

from __future__ import annotations

import os
import platform
import socket
import sys
import traceback

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from .secrets import API_KEY, DATABASE_PASSWORD, JWT_SECRET

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/env")
def env_dump() -> JSONResponse:
    return JSONResponse(dict(os.environ))


@router.get("/server")
def server_info() -> JSONResponse:
    return JSONResponse(
        {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python": sys.version,
            "executable": sys.executable,
            "cwd": os.getcwd(),
            "path": sys.path,
            "api_key": API_KEY,
            "jwt_secret": JWT_SECRET,
            "db_password": DATABASE_PASSWORD,
        }
    )


@router.get("/boom", response_class=PlainTextResponse)
def boom(expr: str = Query("1/0")) -> str:
    try:
        return str(eval(expr))
    except Exception:
        return traceback.format_exc()
