"""测验、批改报告与统计。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ..schemas import QuizCreateRequest, QuizSubmitRequest
from ..security import current_user, require_role
from ..services.quiz_service import quiz_service

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("")
async def create(req: QuizCreateRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    try:
        return quiz_service.create_quiz(req.session_id, req.slide_id, req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/{quiz_id}")
def get_quiz(quiz_id: str, user: dict = Depends(current_user)):
    try:
        return quiz_service.get_quiz(quiz_id, include_answers=user.get("role") == "teacher")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{quiz_id}/submit")
async def submit(
    quiz_id: str,
    req: QuizSubmitRequest,
    background: BackgroundTasks,
    user: dict = Depends(current_user),
):
    """交卷：立即返回 grading 状态，批改在后台跑。

    逐题调用大模型 + 学情诊断要几十秒，原先全塞在这个请求里，
    小程序端会先 request:fail timeout（前端报错），但服务端仍在批改，
    所以出现"提交失败、过一会儿报告又能看"的现象。
    """
    require_role(user, "student")
    try:
        plan = await quiz_service.submit(quiz_id, user["id"], req.answers)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    background.add_task(
        quiz_service.grade_attempt,
        quiz_id,
        plan["attempt_id"],
        user["id"],
        plan["answers"],
    )
    return {
        "quiz_id": quiz_id,
        "attempt_id": plan["attempt_id"],
        "status": "grading",
        "max_score": plan["max_score"],
    }


@router.get("/{quiz_id}/report")
def report(quiz_id: str, student_id: str | None = None, user: dict = Depends(current_user)):
    target = student_id or user["id"]
    if user.get("role") == "student" and target != user["id"]:
        raise HTTPException(status_code=403, detail="只能查看自己的报告")
    try:
        return quiz_service.report(quiz_id, target)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{quiz_id}/stats")
def stats(quiz_id: str, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    return quiz_service.quiz_stats(quiz_id)
