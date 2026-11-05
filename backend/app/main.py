"""FastAPI 入口。"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import assistant, auth, classroom, courseware, diagnosis, quiz, rag, settings as settings_api
from .config import settings
from .mcp_server import mcp
from .seed import init_seed

# MCP Server 挂在 /mcp 上（Streamable HTTP），页面里的 AI 助手通过 MCP Client 调用这些工具
mcp_app = mcp.http_app(path="/", transport="streamable-http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_seed()
    except Exception as exc:  # 示例数据失败时仍允许服务启动，便于排查
        print(f"[Startup] 初始化数据失败: {exc}", file=sys.stderr)
    async with mcp_app.lifespan(app):
        yield


app = FastAPI(
    title="ClassMate AI 课堂助教平台",
    description="多智能体 + RAG 的中小学数学课堂助教后端",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/")
def root():
    return {
        "name": "ClassMate AI 课堂助教平台",
        "docs": "/docs",
        "health": "/api/health",
        "model": settings.model_name,
    }


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "llm_ready": settings.llm_ready,
        "model": settings.model_name,
        "embedding_model": settings.embedding_model,
        "mcp": "/mcp",
    }


app.include_router(auth.router, prefix="/api")
app.include_router(rag.router, prefix="/api")
app.include_router(courseware.router, prefix="/api")
app.include_router(classroom.router, prefix="/api")
app.include_router(quiz.router, prefix="/api")
app.include_router(diagnosis.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")

# 必须在其它路由之后挂载，避免影响 /api 路径匹配
app.mount("/mcp", mcp_app)
