"""账号、密码与令牌（PBKDF2，无第三方依赖）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Query

from . import db


ITERATIONS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, digest_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def create_user(role: str, username: str, password: str, nickname: str) -> dict:
    user_id = f"user_{secrets.token_hex(8)}"
    db.execute(
        "INSERT INTO users(id, role, username, password_hash, nickname, created_at) VALUES(?,?,?,?,?,?)",
        (user_id, role, username.lower(), hash_password(password), nickname, db.now_ms()),
    )
    return get_user(user_id) or {}


def get_user(user_id: str) -> Optional[dict]:
    return db.query_one("SELECT id, role, username, nickname, created_at FROM users WHERE id=?", (user_id,))


def find_by_username(username: str) -> Optional[dict]:
    return db.query_one("SELECT * FROM users WHERE username=?", (username.lower(),))


def authenticate(username: str, password: str) -> Optional[dict]:
    row = find_by_username(username)
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return {k: row[k] for k in ("id", "role", "username", "nickname", "created_at")}


def issue_token(user_id: str) -> str:
    token = secrets.token_hex(24)
    db.execute("INSERT INTO auth_tokens(token, user_id, created_at) VALUES(?,?,?)", (token, user_id, db.now_ms()))
    return token


def user_from_token(token: str) -> Optional[dict]:
    row = db.query_one(
        "SELECT u.id, u.role, u.username, u.nickname FROM auth_tokens t "
        "JOIN users u ON u.id=t.user_id WHERE t.token=?",
        (token,),
    )
    return row


def _token_from_header(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return authorization.strip()


def current_user(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
) -> dict:
    raw = _token_from_header(authorization) or token
    user = user_from_token(raw) if raw else None
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def require_role(user: dict, role: str) -> dict:
    if user.get("role") != role:
        raise HTTPException(status_code=403, detail=f"需要{role}权限")
    return user
