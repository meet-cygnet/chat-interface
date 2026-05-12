"""Template injection (SSTI) and reflected XSS."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
from jinja2 import Template

router = APIRouter(prefix="/render", tags=["render"])


@router.get("/hello", response_class=PlainTextResponse)
def hello(name: str = Query("world")) -> str:
    tpl = Template("Hello, " + name + "!")
    return tpl.render()


@router.get("/page", response_class=HTMLResponse)
def page(name: str = Query("world")) -> str:
    return f"<html><body><h1>Hi {name}</h1></body></html>"


@router.get("/error", response_class=HTMLResponse)
def error(msg: str = Query("")) -> str:
    return "<div class='error'>" + msg + "</div>"


@router.get("/render-template", response_class=PlainTextResponse)
def render_template(tpl: str = Query(...), name: str = Query("world")) -> str:
    return Template(tpl).render(name=name)
