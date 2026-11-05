"""SQLite 数据层（标准库实现，便于离线演示）。"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterable, Iterator

from .config import DB_PATH


def now_ms() -> int:
    return int(time.time() * 1000)


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK(role IN ('teacher','student')),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_spaces (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('textbook','exam','standard','mistake')),
    name TEXT NOT NULL,
    subject TEXT DEFAULT '',
    grade TEXT DEFAULT '',
    textbook_version TEXT DEFAULT '',
    description TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT DEFAULT '',
    file_type TEXT DEFAULT '',
    chunk_count INTEGER DEFAULT 0,
    embedded INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ready',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    document_id TEXT DEFAULT '',
    content TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS exam_items (
    id TEXT PRIMARY KEY,
    space_id TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    grade TEXT DEFAULT '',
    kp TEXT NOT NULL,
    qtype TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK(difficulty IN ('easy','medium','hard')),
    stem TEXT NOT NULL,
    options TEXT NOT NULL DEFAULT '[]',
    answer TEXT NOT NULL,
    analysis TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'sample_adapted',
    year TEXT DEFAULT '',
    region TEXT DEFAULT '',
    derived_from TEXT DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    teacher_id TEXT DEFAULT '',
    title TEXT NOT NULL,
    subject TEXT DEFAULT '',
    grade TEXT DEFAULT '',
    textbook_version TEXT DEFAULT '',
    chapter TEXT DEFAULT '',
    objectives TEXT NOT NULL DEFAULT '[]',
    exam_coverage TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS slides (
    id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    title TEXT NOT NULL,
    bullets TEXT NOT NULL DEFAULT '[]',
    kp TEXT DEFAULT '',
    script TEXT NOT NULL DEFAULT '{}',
    exam_anchor_ids TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS classroom_sessions (
    id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    teacher_id TEXT DEFAULT '',
    class_code TEXT UNIQUE,
    status TEXT DEFAULT 'active',
    current_slide INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS classroom_members (
    session_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    joined_at INTEGER NOT NULL,
    PRIMARY KEY(session_id, student_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    role TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_turns (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    question TEXT NOT NULL,
    image_path TEXT DEFAULT '',
    hint_level INTEGER DEFAULT 0,
    reply TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quizzes (
    id TEXT PRIMARY KEY,
    session_id TEXT DEFAULT '',
    lesson_id TEXT DEFAULT '',
    slide_id TEXT DEFAULT '',
    student_id TEXT DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'class',
    status TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS quiz_items (
    id TEXT PRIMARY KEY,
    quiz_id TEXT NOT NULL,
    exam_item_id TEXT NOT NULL,
    ord INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS quiz_attempts (
    id TEXT PRIMARY KEY,
    quiz_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    max_score INTEGER DEFAULT 100,
    report TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'graded',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    quiz_id TEXT NOT NULL,
    quiz_item_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    answer TEXT DEFAULT '',
    correct INTEGER DEFAULT 0,
    error_type TEXT DEFAULT '',
    feedback TEXT NOT NULL DEFAULT '{}',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS mastery (
    student_id TEXT NOT NULL,
    kp TEXT NOT NULL,
    score REAL DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(student_id, kp)
);

CREATE INDEX IF NOT EXISTS idx_slides_lesson ON slides(lesson_id, ord);
CREATE INDEX IF NOT EXISTS idx_events_session_seq ON events(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_chunks_space ON chunks(space_id);
CREATE INDEX IF NOT EXISTS idx_exam_kp ON exam_items(kp, difficulty);
CREATE INDEX IF NOT EXISTS idx_attempts_student ON attempts(student_id, created_at);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """轻量迁移：老库缺少新字段时自动补上，避免升级后报表接口炸掉。"""
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        # quiz_attempts.status：grading（后台批改中）/ graded（已完成）/ failed（批改失败）
        _ensure_column(conn, "quiz_attempts", "status", "TEXT NOT NULL DEFAULT 'graded'")


def query(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def query_one(sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.lastrowid or cur.rowcount


def execute_many(sql: str, seq: Iterable[Iterable[Any]]) -> None:
    with connect() as conn:
        conn.executemany(sql, [tuple(item) for item in seq])
        conn.commit()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
