"""Shadow endpoints for SAST tool demonstrations.

All routers are aggregated under `vulns_router` and mounted at `/vuln/*` by
`backend.main.create_app()`.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    admin,
    authn,
    crypto,
    debug,
    deserialize,
    files,
    proxy,
    regex_dos,
    render,
    users,
    xml_parser,
)

vulns_router = APIRouter(prefix="/vuln", tags=["vuln"])

vulns_router.include_router(admin.router)
vulns_router.include_router(authn.router)
vulns_router.include_router(crypto.router)
vulns_router.include_router(debug.router)
vulns_router.include_router(deserialize.router)
vulns_router.include_router(files.router)
vulns_router.include_router(proxy.router)
vulns_router.include_router(regex_dos.router)
vulns_router.include_router(render.router)
vulns_router.include_router(users.router)
vulns_router.include_router(xml_parser.router)

__all__ = ["vulns_router"]
