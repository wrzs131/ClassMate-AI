"""运行时可调设置与模型连通性检测。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..llm import llm
from ..schemas import SettingsUpdateRequest
from ..security import current_user, require_role

router = APIRouter(prefix="/settings", tags=["settings"])


def _public_settings() -> dict:
    return {
        "model_name": settings.model_name,
        "embedding_model": settings.embedding_model,
        "base_url": settings.base_url,
        "temperature": settings.temperature,
        "use_llm": settings.use_llm,
        "llm_ready": settings.llm_ready,
        "has_key": bool(settings.api_key),
    }


@router.get("")
def get_settings(user: dict = Depends(current_user)):
    return _public_settings()


@router.put("")
def update_settings(req: SettingsUpdateRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    if req.model_name:
        settings.model_name = req.model_name
    if req.temperature is not None:
        settings.temperature = max(0.0, min(1.5, req.temperature))
    if req.use_llm is not None:
        settings.use_llm = req.use_llm
    llm.invalidate()
    return _public_settings()


@router.post("/test")
async def test_model(user: dict = Depends(current_user)):
    require_role(user, "teacher")
    if not settings.llm_ready:
        raise HTTPException(status_code=400, detail="未配置可用的 API Key，或已关闭 LLM")
    text = await llm.chat("你是连通性测试助手。", "请只回复：连接成功")
    if not text:
        raise HTTPException(status_code=502, detail="模型调用失败，请检查 Key、模型名与网络")
    return {"ok": True, "reply": text[:200], "model": settings.model_name}
