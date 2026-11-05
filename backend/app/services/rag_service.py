"""知识空间、文档解析、Chroma 检索与关键词兜底。"""
from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from .. import db
from ..config import CHROMA_DIR, settings
from ..db import dumps, loads
from ..llm import llm

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception as exc:  # pragma: no cover
    RecursiveCharacterTextSplitter = None  # type: ignore
    print(f"[RAG] 文本分块依赖不可用: {exc}", file=sys.stderr)

# 注意：langchain_chroma 会连带加载 chromadb 的 C/Rust 扩展。
# 部分 Windows 环境的二进制不兼容会直接触发进程崩溃（0xC0000005），无法用 try/except 捕获，
# 因此这里改为“按需导入”：只有 enable_vector=true 时才加载，默认走关键词检索。
_CHROMA_CLASS = None
_CHROMA_TRIED = False


def _chroma_class():
    global _CHROMA_CLASS, _CHROMA_TRIED
    if _CHROMA_TRIED:
        return _CHROMA_CLASS
    _CHROMA_TRIED = True
    try:
        from langchain_chroma import Chroma  # noqa: WPS433

        _CHROMA_CLASS = Chroma
    except Exception as exc:  # pragma: no cover
        _CHROMA_CLASS = None
        print(f"[RAG] 向量依赖不可用，使用关键词检索: {exc}", file=sys.stderr)
    return _CHROMA_CLASS


def _read_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if suffix == ".docx":
        from docx import Document

        document = Document(str(path))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
        return "\n".join(parts)
    raw = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _split_text(text: str, size: int = 520, overlap: int = 80) -> list[str]:
    text = re.sub(r"\r\n", "\n", text).strip()
    if not text:
        return []
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", "；", "！", "？", "，", " "],
        )
        return [c.page_content for c in splitter.create_documents([text]) if c.page_content.strip()]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += max(1, size - overlap)
    return chunks


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9+\-*/×÷=<>|()（）.]", "", text)
    if len(text) <= 2:
        return {text} if text else set()
    return {text[i : i + 2] for i in range(len(text) - 1)}


class RagService:
    def list_spaces(self, kind: Optional[str] = None) -> list[dict]:
        if kind:
            return db.query("SELECT * FROM knowledge_spaces WHERE kind=? ORDER BY created_at", (kind,))
        return db.query("SELECT * FROM knowledge_spaces ORDER BY kind, created_at")

    def get_space(self, space_id: str) -> Optional[dict]:
        return db.query_one("SELECT * FROM knowledge_spaces WHERE id=?", (space_id,))

    def create_space(self, kind: str, name: str, subject: str, grade: str, version: str, description: str) -> dict:
        space_id = f"space_{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO knowledge_spaces(id, kind, name, subject, grade, textbook_version, description, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (space_id, kind, name, subject, grade, version, description, db.now_ms()),
        )
        return self.get_space(space_id) or {}

    def list_documents(self, space_id: str) -> list[dict]:
        return db.query("SELECT * FROM documents WHERE space_id=? ORDER BY created_at DESC", (space_id,))

    def ingest_file(self, space_id: str, path: Path, original_name: str) -> dict:
        space = self.get_space(space_id)
        if not space:
            raise ValueError("知识空间不存在")
        doc_id = f"doc_{uuid.uuid4().hex[:10]}"
        text = _read_text(path)
        chunks = _split_text(text)
        if not chunks:
            raise ValueError("文档中没有可解析的文字")
        db.execute(
            "INSERT INTO documents(id, space_id, name, file_path, file_type, chunk_count, embedded, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (doc_id, space_id, original_name, str(path), path.suffix.lower().lstrip("."), len(chunks), 0, "ready", db.now_ms()),
        )
        for idx, content in enumerate(chunks):
            chunk_id = f"{doc_id}_{idx:02d}"
            metadata = {
                "kind": space["kind"],
                "kp": space.get("subject", ""),
                "source": original_name,
                "document_id": doc_id,
                "space_id": space_id,
            }
            db.execute(
                "INSERT INTO chunks(id, space_id, document_id, content, metadata) VALUES(?,?,?,?,?)",
                (chunk_id, space_id, doc_id, content, dumps(metadata)),
            )
        try:
            self._embed_space(space_id)
            db.execute("UPDATE documents SET embedded=1 WHERE id=?", (doc_id,))
        except Exception as exc:
            print(f"[RAG] 文档已入库，向量化失败（仍可关键词检索）: {exc}", file=sys.stderr)
        return {
            "id": doc_id,
            "space_id": space_id,
            "name": original_name,
            "chunk_count": len(chunks),
            "status": "ready",
        }

    def import_exams(self, space_id: str, items: list[Any]) -> list[str]:
        ids = []
        for item in items:
            data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            exam_id = data.get("id") or f"exam_{uuid.uuid4().hex[:10]}"
            data["id"] = exam_id
            db.execute(
                "INSERT OR REPLACE INTO exam_items(id, space_id, subject, grade, kp, qtype, difficulty, stem, options, "
                "answer, analysis, source, source_type, year, region, derived_from, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    exam_id,
                    space_id,
                    data.get("subject", "数学"),
                    data.get("grade", "七年级"),
                    data["kp"],
                    data.get("qtype", "choice"),
                    data.get("difficulty", "medium"),
                    data["stem"],
                    dumps(data.get("options", [])),
                    data["answer"],
                    data.get("analysis", ""),
                    data.get("source", ""),
                    data.get("source_type", "sample_adapted"),
                    data.get("year", ""),
                    data.get("region", ""),
                    data.get("derived_from", ""),
                    db.now_ms(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO chunks(id, space_id, document_id, content, metadata) VALUES(?,?,?,?,?)",
                (
                    f"examchunk_{exam_id}",
                    space_id,
                    "",
                    f"【{data['kp']}·{data.get('difficulty', 'medium')}】{data['stem']}\n答案：{data['answer']}\n解析：{data.get('analysis', '')}",
                    dumps(
                        {
                            "kind": "exam",
                            "kp": data["kp"],
                            "difficulty": data.get("difficulty", "medium"),
                            "exam_item_id": exam_id,
                            "source": data.get("source", ""),
                            "source_type": data.get("source_type", ""),
                            "space_id": space_id,
                        }
                    ),
                ),
            )
            ids.append(exam_id)
        try:
            self._embed_space(space_id)
        except Exception as exc:
            print(f"[RAG] 真题已入库，向量化失败（仍可关键词检索）: {exc}", file=sys.stderr)
        return ids

    def _collection(self, space_id: str):
        chroma_cls = _chroma_class()
        if chroma_cls is None or not settings.enable_vector:
            return None
        embeddings = llm.embeddings()
        if embeddings is None:
            return None
        return chroma_cls(
            collection_name=f"space_{space_id}",
            embedding_function=embeddings,
            persist_directory=str(CHROMA_DIR),
        )

    def _embed_space(self, space_id: str) -> None:
        collection = self._collection(space_id)
        if collection is None:
            return
        rows = db.query("SELECT id, content, metadata FROM chunks WHERE space_id=?", (space_id,))
        if not rows:
            return
        try:
            existing = collection._collection.count()
        except Exception:
            existing = 0
        if existing >= len(rows):
            return
        texts = [row["content"] for row in rows]
        metadatas = []
        for row in rows:
            meta = loads(row["metadata"], {})
            meta = {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in meta.items()}
            meta.setdefault("space_id", space_id)
            metadatas.append(meta)
        collection.add_texts(texts=texts, metadatas=metadatas, ids=[row["id"] for row in rows])

    def reindex_all(self, only_unembedded: bool = True) -> dict:
        spaces = self.list_spaces()
        result = {}
        if not settings.enable_vector:
            return {space["id"]: "skipped_vector_disabled" for space in spaces}
        for space in spaces:
            if only_unembedded and llm.embeddings() is None:
                result[space["id"]] = "skipped_no_embeddings"
                continue
            try:
                self._embed_space(space["id"])
                result[space["id"]] = "ok"
            except Exception as exc:
                result[space["id"]] = f"failed: {exc}"
        return result

    def search(self, query: str, space_ids: list[str] | None = None, kind: str | None = None, kp: str | None = None, top_k: int = 5) -> list[dict]:
        query = (query or "").strip()
        if not query:
            return []
        spaces = self.list_spaces()
        if space_ids:
            spaces = [s for s in spaces if s["id"] in space_ids]
        if kind:
            spaces = [s for s in spaces if s["kind"] == kind]

        hits: list[dict] = []
        if settings.enable_vector and _chroma_class() is not None and llm.embeddings() is not None:
            for space in spaces:
                try:
                    collection = self._collection(space["id"])
                    if collection is None:
                        continue
                    docs = collection.similarity_search_with_score(query, k=max(top_k * 3, 8))
                except Exception as exc:
                    print(f"[RAG] Chroma 检索失败，切换关键词: {exc}", file=sys.stderr)
                    docs = []
                for doc, score in docs:
                    meta = doc.metadata or {}
                    if kp and kp not in str(meta.get("kp", "")) and kp not in doc.page_content:
                        continue
                    hits.append(
                        {
                            "chunk_id": meta.get("chunk_id") or "",
                            "content": doc.page_content,
                            "score": float(1 - score) if isinstance(score, (int, float)) else 0.0,
                            "source": meta.get("source", ""),
                            "kind": meta.get("kind", space["kind"]),
                            "metadata": meta,
                        }
                    )

        if len(hits) < top_k:
            sql_parts = []
            params: list[Any] = []
            if spaces:
                placeholders = ",".join("?" for _ in spaces)
                sql_parts.append(f"space_id IN ({placeholders})")
                params.extend([s["id"] for s in spaces])
            sql = "SELECT id, space_id, content, metadata FROM chunks"
            if sql_parts:
                sql += " WHERE " + " AND ".join(sql_parts)
            rows = db.query(sql, params)
            query_grams = _bigrams(query)
            for row in rows:
                meta = loads(row["metadata"], {})
                if kp and kp not in str(meta.get("kp", "")) and kp not in row["content"]:
                    continue
                grams = _bigrams(row["content"])
                overlap = len(query_grams & grams)
                if overlap == 0:
                    continue
                score = overlap / max(1, len(query_grams))
                if kp and kp in row["content"]:
                    score += 0.2
                hits.append(
                    {
                        "chunk_id": row["id"],
                        "content": row["content"],
                        "score": round(score, 4),
                        "source": meta.get("source", ""),
                        "kind": meta.get("kind", ""),
                        "metadata": meta,
                    }
                )
            hits.sort(key=lambda h: h["score"], reverse=True)
            hits = hits[:top_k]
        return hits[:top_k]


rag_service = RagService()
