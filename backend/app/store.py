"""PostgreSQL persistence for sessions and messages (plain SQL, pure-Python driver)."""
import json
import uuid

from .db import connect, run


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def create_session(user_meta: dict | None = None) -> dict:
    sid = str(uuid.uuid4())
    conn = connect()
    try:
        row = run(conn, "INSERT INTO sessions (id, user_meta) VALUES (%s, %s::jsonb) "
                        "RETURNING id, title, created_at, updated_at", (sid, json.dumps(user_meta or {}))).fetchone()
    finally:
        conn.close()
    return {"id": row[0], "title": row[1], "created_at": _iso(row[2]), "updated_at": _iso(row[3])}


def list_sessions(limit: int = 50) -> list[dict]:
    conn = connect()
    try:
        rows = run(conn, "SELECT id, title, created_at, updated_at FROM sessions "
                         "ORDER BY updated_at DESC LIMIT %s", (limit,)).fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "title": r[1], "created_at": _iso(r[2]), "updated_at": _iso(r[3])} for r in rows]


def get_session(sid: str) -> dict | None:
    conn = connect()
    try:
        s = run(conn, "SELECT id, title, created_at, updated_at FROM sessions WHERE id=%s", (sid,)).fetchone()
        if not s:
            return None
        msgs = run(conn, "SELECT id, role, content, route, provider, model, sources, artifact, latency_ms, created_at "
                         "FROM messages WHERE session_id=%s ORDER BY id", (sid,)).fetchall()
    finally:
        conn.close()
    return {"id": s[0], "title": s[1], "created_at": _iso(s[2]), "updated_at": _iso(s[3]),
            "messages": [{"id": m[0], "role": m[1], "content": m[2], "route": m[3], "provider": m[4],
                          "model": m[5], "sources": m[6] or [], "artifact": m[7], "latency_ms": m[8],
                          "created_at": _iso(m[9])} for m in msgs]}


def delete_session(sid: str) -> bool:
    conn = connect()
    try:
        cur = run(conn, "DELETE FROM sessions WHERE id=%s", (sid,))
        return cur.rowcount > 0
    finally:
        conn.close()


def add_message(sid: str, role: str, content: str, *, route=None, provider=None, model=None,
                sources=None, artifact=None, latency_ms=None) -> int:
    conn = connect()
    try:
        mid = run(conn, "INSERT INTO messages (session_id, role, content, route, provider, model, sources, artifact, latency_ms) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
                  (sid, role, content, route, provider, model, json.dumps(sources or []),
                   json.dumps(artifact) if artifact else None, latency_ms)).fetchone()[0]
        run(conn, "UPDATE sessions SET updated_at = now() WHERE id=%s", (sid,))
        if role == "user":  # first user message names the chat
            run(conn, "UPDATE sessions SET title = %s WHERE id=%s AND title='New chat'",
                (content.strip().replace("\n", " ")[:60], sid))
        return mid
    finally:
        conn.close()


def history(sid: str, limit: int = 40) -> list[dict]:
    conn = connect()
    try:
        rows = run(conn, "SELECT role, content, sources, artifact FROM ("
                         " SELECT id, role, content, sources, artifact FROM messages WHERE session_id=%s "
                         " ORDER BY id DESC LIMIT %s) t ORDER BY id", (sid, limit)).fetchall()
    finally:
        conn.close()
    return [{"role": r[0], "content": r[1], "sources": r[2] or [], "artifact": r[3]} for r in rows]


def index_stats() -> dict:
    conn = connect()
    try:
        e = run(conn, "SELECT count(*) FROM episodes").fetchone()[0]
        c = run(conn, "SELECT count(*) FROM chunks").fetchone()[0]
    finally:
        conn.close()
    return {"episodes": e, "chunks": c}
