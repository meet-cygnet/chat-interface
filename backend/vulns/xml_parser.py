"""XML parsing — XXE via lxml with external entities allowed."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from lxml import etree

router = APIRouter(prefix="/xml", tags=["xml"])


@router.post("/parse", response_class=PlainTextResponse)
async def parse_xml(request: Request) -> str:
    body = await request.body()
    parser = etree.XMLParser(resolve_entities=True, no_network=False, load_dtd=True)
    root = etree.fromstring(body, parser=parser)
    return etree.tostring(root, pretty_print=True).decode()


@router.post("/xpath", response_class=PlainTextResponse)
async def xpath_query(request: Request) -> str:
    payload = await request.json()
    xml = payload.get("xml", "")
    expr = payload.get("expr", "/")
    root = etree.fromstring(xml.encode())
    results = root.xpath(expr)  # caller-controlled XPath
    return repr(results)
