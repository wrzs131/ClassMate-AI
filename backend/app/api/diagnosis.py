"""学情诊断接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..security import current_user
from ..services.diagnosis_service import diagnosis_service

router = APIRouter(tags=["diagnosis"])


@router.get("/students/{student_id}/diagnosis")
def student_diagnosis(student_id: str, user: dict = Depends(current_user)):
    if user.get("role") == "student" and student_id != user["id"]:
        raise HTTPException(status_code=403, detail="只能查看自己的学情")
    return diagnosis_service.student_report(student_id)


@router.get("/me/diagnosis")
def my_diagnosis(user: dict = Depends(current_user)):
    return diagnosis_service.student_report(user["id"])


@router.get("/sessions/{session_id}/class-report")
def class_report(session_id: str, user: dict = Depends(current_user)):
    if user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="需要教师权限")
    return diagnosis_service.class_report(session_id)
