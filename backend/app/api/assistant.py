"""教师端 AI 助手（MCP 工具模式）接口。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from .. import db
from ..agent import assistant_agent, list_tool_meta
from ..config import settings
from ..schemas import AssistantChatRequest
from ..security import current_user, require_role

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/tools")
async def tools(user: dict = Depends(current_user)):
    require_role(user, "teacher")
    return {"tools": await list_tool_meta(), "llm_ready": settings.llm_ready, "mode": "mcp"}


@router.post("/chat")
async def chat(req: AssistantChatRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="请输入一句话再发送")
    try:
        return await assistant_agent.chat(
            user["id"],
            req.message,
            [item.model_dump() for item in req.history],
            req.tools_enabled,
            req.confirm_token,
            req.conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # 模型 / MCP 异常统一兜底，避免前端看到堆栈
        raise HTTPException(status_code=502, detail=f"AI 助手暂时不可用：{exc}")


@router.get("/conversations")
def conversations(limit: int = 20, user: dict = Depends(current_user)):
    """当前教师的历史对话列表（按最近活跃排序）。"""
    require_role(user, "teacher")
    rows = db.query(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM assistant_messages m WHERE m.conversation_id=c.id) AS message_count,
               (SELECT m.content FROM assistant_messages m
                 WHERE m.conversation_id=c.id ORDER BY m.created_at DESC, m.rowid DESC LIMIT 1) AS last_message
        FROM assistant_conversations c
        WHERE c.user_id=?
        ORDER BY c.updated_at DESC
        LIMIT ?
        """,
        (user["id"], max(1, min(limit, 50))),
    )
    return {"conversations": rows}


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, user: dict = Depends(current_user)):
    """读取某个历史对话的全部消息，用于前端切换会话。"""
    require_role(user, "teacher")
    conv = db.query_one(
        "SELECT id, title, created_at, updated_at FROM assistant_conversations WHERE id=? AND user_id=?",
        (conversation_id, user["id"]),
    )
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    rows = db.query(
        "SELECT role, content, tool_calls, created_at FROM assistant_messages "
        "WHERE conversation_id=? AND user_id=? ORDER BY created_at ASC, rowid ASC",
        (conversation_id, user["id"]),
    )
    messages = []
    for row in rows:
        try:
            calls = json.loads(row.get("tool_calls") or "[]")
        except json.JSONDecodeError:
            calls = []
        messages.append(
            {"role": row["role"], "content": row["content"], "tool_calls": calls, "created_at": row["created_at"]}
        )
    return {"conversation": conv, "messages": messages}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: dict = Depends(current_user)):
    """删除一条历史对话及其全部消息（仅限当前教师本人的对话）。"""
    require_role(user, "teacher")
    conv = db.query_one(
        "SELECT id FROM assistant_conversations WHERE id=? AND user_id=?",
        (conversation_id, user["id"]),
    )
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.execute(
        "DELETE FROM assistant_messages WHERE conversation_id=? AND user_id=?",
        (conversation_id, user["id"]),
    )
    db.execute(
        "DELETE FROM assistant_conversations WHERE id=? AND user_id=?",
        (conversation_id, user["id"]),
    )
    return {"ok": True, "deleted": conversation_id}
