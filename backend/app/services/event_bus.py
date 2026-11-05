"""课堂事件总线：统一 seq、写入 SQLite、供 SSE/轮询读取。"""
from __future__ import annotations

from typing import Any

from .. import db
from ..db import dumps, loads


def append_event(session_id: str, event_type: str, role: str, payload: dict[str, Any]) -> dict:
    row = db.query_one("SELECT COALESCE(MAX(seq), 0) AS seq FROM events WHERE session_id=?", (session_id,))
    seq = int(row["seq"]) + 1 if row else 1
    db.execute(
        "INSERT INTO events(session_id, seq, type, role, payload, created_at) VALUES(?,?,?,?,?,?)",
        (session_id, seq, event_type, role, dumps(payload), db.now_ms()),
    )
    return {"seq": seq, "type": event_type, "role": role, "payload": payload}


def list_events(session_id: str, after_seq: int = 0, limit: int = 100) -> list[dict]:
    rows = db.query(
        "SELECT seq, type, role, payload, created_at FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT ?",
        (session_id, after_seq, limit),
    )
    for row in rows:
        row["payload"] = loads(row.get("payload"), {})
    return rows
