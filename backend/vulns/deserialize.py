"""Insecure deserialization — pickle, yaml, shelve."""

from __future__ import annotations

import base64
import pickle
import shelve

import yaml
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

router = APIRouter(prefix="/deser", tags=["deser"])


@router.post("/pickle")
async def load_pickle(request: Request) -> JSONResponse:
    raw = await request.body()
    data = pickle.loads(base64.b64decode(raw))
    return JSONResponse({"type": type(data).__name__, "repr": repr(data)})


@router.get("/cookie")
def load_cookie(token: str = Query(...)) -> JSONResponse:
    data = pickle.loads(base64.b64decode(token))
    return JSONResponse({"value": repr(data)})


@router.post("/yaml")
async def load_yaml(request: Request) -> JSONResponse:
    body = (await request.body()).decode("utf-8", errors="ignore")
    data = yaml.load(body, Loader=yaml.Loader)
    return JSONResponse({"value": repr(data)})


@router.get("/shelve", response_class=PlainTextResponse)
def open_shelve(path: str = Query(...), key: str = Query("data")) -> str:
    with shelve.open(path) as db:
        return repr(db.get(key))
