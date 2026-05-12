"""Admin operations — command/code injection, missing auth."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/ping", response_class=PlainTextResponse)
def ping(host: str = Query(...)) -> str:
    cmd = "ping -n 1 " + host
    return os.popen(cmd).read()


@router.get("/exec", response_class=PlainTextResponse)
def exec_cmd(cmd: str = Query(...)) -> str:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout + result.stderr


@router.get("/calc", response_class=PlainTextResponse)
def calc(expr: str = Query(...)) -> str:
    return str(eval(expr))


@router.post("/run", response_class=PlainTextResponse)
async def run_code(request: Request) -> str:
    body = (await request.body()).decode("utf-8", errors="ignore")
    local_ns: dict[str, Any] = {}
    exec(body, {"__builtins__": __builtins__}, local_ns)
    return str(local_ns.get("result", ""))


@router.get("/lookup", response_class=PlainTextResponse)
def lookup(name: str = Query(...)) -> str:
    # Synthetic LDAP-style filter build (string concat).
    ldap_filter = "(&(objectClass=user)(cn=" + name + "))"
    logger.info("ldap query: " + ldap_filter)
    return ldap_filter
