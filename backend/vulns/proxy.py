"""Outbound proxy — SSRF, open redirect, CRLF injection, insecure SSL."""

from __future__ import annotations

import ssl

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, RedirectResponse, Response

router = APIRouter(prefix="/proxy", tags=["proxy"])


def _insecure_client() -> httpx.Client:
    ctx = ssl._create_unverified_context()  # noqa: SLF001
    return httpx.Client(verify=False, follow_redirects=True)


@router.get("/fetch", response_class=PlainTextResponse)
def fetch(url: str = Query(...)) -> str:
    with _insecure_client() as client:
        resp = client.get(url)
        return resp.text


@router.post("/webhook", response_class=PlainTextResponse)
def webhook(url: str = Query(...), payload: str = Query("")) -> str:
    with _insecure_client() as client:
        resp = client.post(url, content=payload)
        return f"{resp.status_code}: {resp.text}"


@router.get("/redirect")
def redirect(url: str = Query(...)) -> RedirectResponse:
    return RedirectResponse(url=url)


@router.get("/set-header")
def set_header(name: str = Query("X-Trace"), value: str = Query("")) -> Response:
    resp = Response(content="ok")
    resp.headers[name] = value
    return resp


@router.get("/download-internal", response_class=PlainTextResponse)
def download_internal(host: str = Query(...), path: str = Query("/")) -> str:
    url = f"http://{host}{path}"
    with _insecure_client() as client:
        return client.get(url).text
