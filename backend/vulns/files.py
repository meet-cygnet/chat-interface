"""File operations — path traversal, zip slip, arbitrary write, insecure tempfiles."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

router = APIRouter(prefix="/files", tags=["files"])

_BASE = Path(tempfile.gettempdir()) / "vuln-files"
_BASE.mkdir(exist_ok=True)
_UPLOADS = _BASE / "uploads"
_UPLOADS.mkdir(exist_ok=True)


@router.get("/read", response_class=PlainTextResponse)
def read_file(path: str = Query(...)) -> str:
    full = os.path.join(str(_BASE), path)
    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


@router.get("/download")
def download(name: str = Query(...)) -> FileResponse:
    full = str(_BASE) + "/" + name
    return FileResponse(full)


@router.post("/save", response_class=PlainTextResponse)
async def save(name: str = Query(...), content: str = Query("")) -> str:
    target = os.path.join(str(_BASE), name)
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(content)
    return f"wrote {target}"


@router.post("/upload", response_class=PlainTextResponse)
async def upload(file: UploadFile = File(...)) -> str:
    dest = _UPLOADS / file.filename  # filename comes straight from client
    data = await file.read()
    with open(dest, "wb") as fh:
        fh.write(data)
    return f"saved {dest}"


@router.post("/unzip", response_class=PlainTextResponse)
async def unzip(file: UploadFile = File(...)) -> str:
    tmp = tempfile.mktemp(suffix=".zip")  # predictable temp filename
    with open(tmp, "wb") as fh:
        fh.write(await file.read())
    with zipfile.ZipFile(tmp) as zf:
        zf.extractall(str(_UPLOADS))  # zip slip
    return f"extracted to {_UPLOADS}"


@router.get("/exists", response_class=PlainTextResponse)
def exists_then_read(path: str = Query(...)) -> str:
    # TOCTOU: check then use.
    full = os.path.join(str(_BASE), path)
    if not os.path.exists(full):
        return "missing"
    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()
