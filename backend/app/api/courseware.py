"""备课与课件接口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..schemas import CoursewareRequest, ExportRequest, SlidePatch
from ..security import current_user, require_role
from ..services.courseware_service import courseware_service

router = APIRouter(prefix="/courseware", tags=["courseware"])


@router.post("/generate")
async def generate(req: CoursewareRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    try:
        return await courseware_service.generate(req.model_dump(), user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("")
def list_lessons(user: dict = Depends(current_user)):
    lessons = courseware_service.list_lessons(user["id"] if user.get("role") == "teacher" else None)
    return {"lessons": lessons}


@router.get("/{lesson_id}")
def get_lesson(lesson_id: str, user: dict = Depends(current_user)):
    try:
        return courseware_service.get_lesson(lesson_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{lesson_id}/slides/{slide_id}")
def patch_slide(lesson_id: str, slide_id: str, patch: SlidePatch, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    try:
        return courseware_service.update_slide(lesson_id, slide_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{lesson_id}/export")
def export(lesson_id: str, req: ExportRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    try:
        path = courseware_service.export(lesson_id, req.format)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return FileResponse(
        path=str(path),
        filename=Path(path).name,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
        if req.format == "pptx"
        else "application/json",
    )
