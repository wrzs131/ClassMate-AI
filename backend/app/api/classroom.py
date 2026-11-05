"""课堂：开课、加入、推进、答疑、总结、SSE 与看板。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .. import db
from ..schemas import AdvanceRequest, AskRequest, ClassroomCreateRequest, ClassroomJoinRequest
from ..security import current_user, require_role
from ..services.classroom_service import classroom_service

router = APIRouter(prefix="/classroom", tags=["classroom"])


def _session_or_404(session_id: str) -> dict:
    session = db.query_one("SELECT * FROM classroom_sessions WHERE id=?", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="课堂不存在")
    return session


def _ensure_access(session_id: str, user: dict) -> dict:
    session = _session_or_404(session_id)
    if user.get("role") == "teacher":
        if session["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="无权访问该课堂")
    else:
        if not db.query_one(
            "SELECT 1 FROM classroom_members WHERE session_id=? AND student_id=?", (session_id, user["id"])
        ):
            raise HTTPException(status_code=403, detail="请先通过课堂码加入课堂")
    return session


@router.post("")
async def create(req: ClassroomCreateRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    try:
        return classroom_service.create_session(req.lesson_id, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/join")
async def join(req: ClassroomJoinRequest, user: dict = Depends(current_user)):
    require_role(user, "student")
    try:
        return classroom_service.join(req.class_code, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_sessions(user: dict = Depends(current_user)):
    require_role(user, "teacher")
    return {"sessions": classroom_service.list_sessions(user["id"])}


@router.post("/{session_id}/leave")
async def leave(session_id: str, user: dict = Depends(current_user)):
    """学生退出课堂（幂等）：退出后教师端立即看到「某某 退出课堂」。"""
    require_role(user, "student")
    _session_or_404(session_id)
    try:
        return classroom_service.leave(session_id, user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}/state")
def state(session_id: str, after_seq: int = 0, user: dict = Depends(current_user)):
    _ensure_access(session_id, user)
    try:
        return classroom_service.state(session_id, user, after_seq)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{session_id}/advance")
async def advance(session_id: str, req: AdvanceRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    _ensure_access(session_id, user)
    try:
        return await classroom_service.advance(session_id, user["id"], req.include_quiz)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/ask")
async def ask(session_id: str, req: AskRequest, user: dict = Depends(current_user)):
    _ensure_access(session_id, user)
    if user.get("role") != "student":
        raise HTTPException(status_code=403, detail="该接口供学生提问使用")
    try:
        return await classroom_service.ask(session_id, user["id"], req.question, req.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{session_id}/summary")
async def summary(session_id: str, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    _ensure_access(session_id, user)
    try:
        text = await classroom_service.summary(session_id, user["id"])
        return {"summary": text}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{session_id}/close")
async def close(session_id: str, user: dict = Depends(current_user)):
    """关闭当前课堂（归档）：课堂码失效，教师可重新开课生成新的课堂码。"""
    require_role(user, "teacher")
    _ensure_access(session_id, user)
    try:
        return classroom_service.close_session(session_id, user["id"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}/dashboard")
def dashboard(session_id: str, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    _ensure_access(session_id, user)
    try:
        return classroom_service.dashboard(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{session_id}/stream")
async def stream(session_id: str, after_seq: int = 0, user: dict = Depends(current_user)):
    _ensure_access(session_id, user)
    return StreamingResponse(
        classroom_service.event_stream(session_id, after_seq),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
