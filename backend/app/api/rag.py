"""知识库：空间、上传、真题导入、检索与重建索引。"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from .. import db
from ..config import UPLOAD_DIR
from ..schemas import ExamImportRequest, RagSearchRequest, SpaceCreateRequest
from ..security import current_user, require_role
from ..services import question_bank
from ..services.rag_service import rag_service

router = APIRouter(prefix="/rag", tags=["rag"])

ALLOWED_SUFFIX = {".pdf", ".docx", ".txt", ".md"}


@router.get("/spaces")
def list_spaces(user: dict = Depends(current_user)):
    return {"spaces": rag_service.list_spaces()}


@router.post("/spaces")
def create_space(req: SpaceCreateRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    space = rag_service.create_space(req.kind, req.name, req.subject, req.grade, req.textbook_version, req.description)
    return space


@router.get("/spaces/{space_id}/documents")
def list_documents(space_id: str, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    return {"documents": rag_service.list_documents(space_id)}


@router.post("/spaces/{space_id}/upload")
async def upload(space_id: str, file: UploadFile = File(...), user: dict = Depends(current_user)):
    require_role(user, "teacher")
    space = rag_service.get_space(space_id)
    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIX:
        raise HTTPException(status_code=400, detail=f"暂支持 {', '.join(sorted(ALLOWED_SUFFIX))}")
    data = await file.read()
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件不能超过 30MB")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}{suffix}"
    dest.write_bytes(data)
    try:
        doc = rag_service.ingest_file(space_id, dest, file.filename or dest.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return doc


@router.post("/spaces/{space_id}/import-exams")
def import_exams(space_id: str, req: ExamImportRequest, user: dict = Depends(current_user)):
    require_role(user, "teacher")
    space = rag_service.get_space(space_id)
    if not space:
        raise HTTPException(status_code=404, detail="知识空间不存在")
    ids = rag_service.import_exams(space_id, req.items)
    return {"imported": len(ids), "ids": ids}


@router.post("/search")
def search(req: RagSearchRequest, user: dict = Depends(current_user)):
    hits = rag_service.search(req.query, req.space_ids, req.kind, req.kp, req.top_k)
    return {"hits": hits}


@router.get("/exams")
def list_exams(
    kp: str | None = None,
    difficulty: str | None = None,
    limit: int = 50,
    user: dict = Depends(current_user),
):
    require_role(user, "teacher")
    items = question_bank.list_items(kp=kp, difficulty=difficulty, limit=limit)
    return {"items": items, "total": len(items)}


@router.post("/reindex")
def reindex(user: dict = Depends(current_user)):
    require_role(user, "teacher")
    result = rag_service.reindex_all(only_unembedded=False)
    return {"result": result}


@router.get("/stats")
def rag_stats(user: dict = Depends(current_user)):
    require_role(user, "teacher")
    spaces = rag_service.list_spaces()
    return {
        "spaces": spaces,
        "chunks": db.query_one("SELECT COUNT(*) AS n FROM chunks")["n"],
        "documents": db.query_one("SELECT COUNT(*) AS n FROM documents")["n"],
        "exam_items": db.query_one("SELECT COUNT(*) AS n FROM exam_items")["n"],
    }
