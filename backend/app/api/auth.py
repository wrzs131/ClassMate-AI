"""账号注册、登录与当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import security
from ..schemas import LoginRequest, RegisterRequest
from ..security import current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(req: RegisterRequest):
    if security.find_by_username(req.username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = security.create_user(req.role, req.username, req.password, req.nickname)
    token = security.issue_token(user["id"])
    return {"token": token, "user": user}


@router.post("/login")
def login(req: LoginRequest):
    user = security.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    token = security.issue_token(user["id"])
    return {"token": token, "user": user}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return user
