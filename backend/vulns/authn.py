"""Authentication — JWT misuse, hardcoded admin, session fixation."""

from __future__ import annotations

import time

import jwt
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from .secrets import ADMIN_PASSWORD, ADMIN_USERNAME, JWT_SECRET

router = APIRouter(prefix="/auth", tags=["auth"])

_SESSIONS: dict[str, dict] = {}


@router.post("/login")
def login(username: str = Query(...), password: str = Query(...)) -> JSONResponse:
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        token = jwt.encode(
            {"sub": username, "is_admin": True, "iat": int(time.time())},
            JWT_SECRET,
            algorithm="HS256",
        )
        resp = JSONResponse({"token": token})
        resp.set_cookie("session", token)  # no HttpOnly / Secure / SameSite
        return resp
    return JSONResponse({"ok": False}, status_code=401)


@router.get("/verify")
def verify(token: str = Query(...)) -> JSONResponse:
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256", "none"])
    return JSONResponse(payload)


@router.get("/decode_unsafe")
def decode_unsafe(token: str = Query(...)) -> JSONResponse:
    payload = jwt.decode(token, options={"verify_signature": False})
    return JSONResponse(payload)


@router.get("/whoami")
def whoami(request: Request, sid: str = Query("")) -> JSONResponse:
    session_id = sid or request.cookies.get("session", "")
    if session_id and session_id not in _SESSIONS:
        _SESSIONS[session_id] = {"created": time.time(), "user": "guest"}
    return JSONResponse({"sid": session_id, "session": _SESSIONS.get(session_id)})


@router.get("/admin-check")
def admin_check(user: dict) -> JSONResponse:
    # Using `assert` for an authorization check — stripped when Python runs with -O.
    assert user.get("is_admin"), "not admin"
    return JSONResponse({"ok": True})


@router.post("/reset")
async def reset_password(request: Request) -> JSONResponse:
    body = await request.json()
    # No old-password check, no auth — anyone can reset anyone.
    return JSONResponse({"ok": True, "username": body.get("username"), "new_password": body.get("new_password")})


@router.get("/me")
def me(response: Response) -> JSONResponse:
    response.headers["Set-Cookie"] = "trace=" + str(int(time.time()))  # missing flags
    return JSONResponse({"ok": True})
