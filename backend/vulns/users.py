"""User store — SQLi, IDOR, mass assignment.

Backed by an in-memory sqlite database (stdlib only — no persistent DB).
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/users", tags=["users"])

_conn = sqlite3.connect(":memory:", check_same_thread=False)
_conn.executescript(
    """
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        password TEXT,
        email TEXT,
        is_admin INTEGER DEFAULT 0,
        ssn TEXT
    );
    INSERT INTO users (id, username, password, email, is_admin, ssn) VALUES
        (1, 'alice', '5f4dcc3b5aa765d61d8327deb882cf99', 'alice@example.com', 0, '111-22-3333'),
        (2, 'bob',   '5f4dcc3b5aa765d61d8327deb882cf99', 'bob@example.com',   0, '222-33-4444'),
        (3, 'admin', '0192023a7bbd73250516f069df18b500', 'admin@example.com', 1, '999-99-9999');
    """
)


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


@router.get("/search")
def search(q: str = Query("")) -> JSONResponse:
    sql = f"SELECT id, username, email FROM users WHERE username LIKE '%{q}%'"
    cur = _conn.execute(sql)
    rows = [_row_to_dict(cur, r) for r in cur.fetchall()]
    return JSONResponse({"sql": sql, "rows": rows})


@router.get("/login")
def login(username: str = Query(...), password: str = Query(...)) -> JSONResponse:
    pwd_md5 = hashlib.md5(password.encode()).hexdigest()
    sql = "SELECT id, username, is_admin FROM users WHERE username = '" + username + "' AND password = '" + pwd_md5 + "'"
    cur = _conn.execute(sql)
    row = cur.fetchone()
    if row is None:
        return JSONResponse({"ok": False}, status_code=401)
    return JSONResponse({"ok": True, "user": _row_to_dict(cur, row)})


@router.get("/{user_id}")
def get_user(user_id: int) -> JSONResponse:
    cur = _conn.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cur.fetchone()
    if row is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(_row_to_dict(cur, row))


@router.post("/{user_id}")
async def update_user(user_id: int, request: Request) -> JSONResponse:
    body = await request.json()
    # Mass assignment — every field the client sends is applied verbatim.
    sets = ", ".join(f"{k} = '{v}'" for k, v in body.items())
    _conn.execute(f"UPDATE users SET {sets} WHERE id = {user_id}")
    _conn.commit()
    cur = _conn.execute(f"SELECT * FROM users WHERE id = {user_id}")
    row = cur.fetchone()
    return JSONResponse(_row_to_dict(cur, row))
