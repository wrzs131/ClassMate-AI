"""首次启动的示例数据：账号、知识空间、教材片段、参考试卷题。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import db, security
from .config import DB_PATH, SEED_DIR
from .db import dumps


TEXTBOOK_DOC_ID = "doc_seed_textbook_g7"
STANDARD_DOC_ID = "doc_seed_standard_g7"


def _upsert_user(role: str, username: str, password: str, nickname: str) -> None:
    if db.query_one("SELECT id FROM users WHERE username=?", (username,)):
        return
    db.execute(
        "INSERT INTO users(id, role, username, password_hash, nickname, created_at) VALUES(?,?,?,?,?,?)",
        (f"user_{username}", role, username, security.hash_password(password), nickname, db.now_ms()),
    )


def _ensure_space(space_id: str, kind: str, name: str, description: str) -> None:
    if db.query_one("SELECT id FROM knowledge_spaces WHERE id=?", (space_id,)):
        return
    db.execute(
        "INSERT INTO knowledge_spaces(id, kind, name, subject, grade, textbook_version, description, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (space_id, kind, name, "数学", "七年级", "北师大版（2026）", description, db.now_ms()),
    )


def _textbook_chunks() -> list[dict]:
    path = SEED_DIR / "textbook_g7_rational_add_sub.md"
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"\n##\s+", text)
    chunks = []
    for idx, section in enumerate(sections):
        lines = section.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip().replace("#", "").strip()
        body = "\n".join(lines[1:]).strip()
        if not body:
            continue
        kp = "有理数的加减运算"
        if "加法" in title:
            kp = "有理数的加法"
        if "减法" in title:
            kp = "有理数的减法"
        if "混合" in title:
            kp = "有理数加减混合运算"
        if "数轴" in title or "绝对值" in title:
            kp = "数轴与绝对值"
        if "易错" in title:
            kp = "有理数加减混合运算"
        if "生活" in title:
            kp = "有理数加减应用"
        chunks.append(
            {
                "id": f"tb_{idx:02d}",
                "content": f"【{title}】\n{body}",
                "metadata": {
                    "kind": "textbook",
                    "kp": kp,
                    "section": title,
                    "source": "示例教材片段（课标对齐，非官方原文）",
                    "document_id": TEXTBOOK_DOC_ID,
                },
            }
        )
    return chunks


def _standard_chunks() -> list[dict]:
    text = (
        "《义务教育数学课程标准（2022 年版）》七年级“数与代数”要求：理解有理数的意义，"
        "能用数轴上的点表示有理数，能比较有理数的大小；理解有理数的加法与减法运算，"
        "能熟练进行有理数的加减运算，并能运用有理数加减解决简单的实际问题；"
        "在运算过程中体会转化思想，养成检验与反思的习惯。"
    )
    return [
        {
            "id": "std_01",
            "content": text,
            "metadata": {
                "kind": "standard",
                "kp": "有理数的加减运算",
                "source": "课程标准示例片段",
                "document_id": STANDARD_DOC_ID,
            },
        }
    ]


def _insert_chunks(chunks: list[dict]) -> None:
    for chunk in chunks:
        db.execute(
            "INSERT OR REPLACE INTO chunks(id, space_id, document_id, content, metadata) VALUES(?,?,?,?,?)",
            (
                chunk["id"],
                "space_textbook" if chunk["metadata"]["kind"] == "textbook" else "space_standard",
                chunk["metadata"].get("document_id", ""),
                chunk["content"],
                dumps(chunk["metadata"]),
            ),
        )


def _insert_exam_items() -> None:
    path = SEED_DIR / "exam_items.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    for item in items:
        db.execute(
            "INSERT OR REPLACE INTO exam_items(id, space_id, subject, grade, kp, qtype, difficulty, stem, options, "
            "answer, analysis, source, source_type, year, region, derived_from, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item["id"],
                "space_exam",
                item.get("subject", "数学"),
                item.get("grade", "七年级"),
                item["kp"],
                item.get("qtype", "choice"),
                item["difficulty"],
                item["stem"],
                dumps(item.get("options", [])),
                item["answer"],
                item.get("analysis", ""),
                item.get("source", ""),
                item.get("source_type", "sample_adapted"),
                item.get("year", ""),
                item.get("region", ""),
                item.get("derived_from", ""),
                db.now_ms(),
            ),
        )
        db.execute(
            "INSERT OR REPLACE INTO chunks(id, space_id, document_id, content, metadata) VALUES(?,?,?,?,?)",
            (
                f"examchunk_{item['id']}",
                "space_exam",
                "",
                f"【{item['kp']}·{item['difficulty']}】{item['stem']}\n答案：{item['answer']}\n解析：{item.get('analysis', '')}",
                dumps(
                    {
                        "kind": "exam",
                        "kp": item["kp"],
                        "difficulty": item["difficulty"],
                        "exam_item_id": item["id"],
                        "source": item.get("source", ""),
                        "source_type": item.get("source_type", ""),
                    }
                ),
            ),
        )


def init_seed() -> None:
    db.init_db()
    _upsert_user("teacher", "teacher", "demo123456", "王老师")
    _upsert_user("student", "student", "demo123456", "小明")
    _upsert_user("student", "student2", "demo123456", "小红")
    _ensure_space("space_textbook", "textbook", "七年级数学·教材库", "教材与讲义片段，用于备课与讲解引用")
    _ensure_space("space_exam", "exam", "七年级数学·真题/参考试卷库", "参考试卷与课标对齐示例题，用于组卷与推送")
    _ensure_space("space_standard", "standard", "七年级数学·课标库", "课程标准与素养要求")
    _insert_chunks(_textbook_chunks())
    _insert_chunks(_standard_chunks())
    _insert_exam_items()

    # 文档元数据（种子教材在知识库中可见）
    if not db.query_one("SELECT id FROM documents WHERE id=?", (TEXTBOOK_DOC_ID,)):
        db.execute(
            "INSERT INTO documents(id, space_id, name, file_path, file_type, chunk_count, embedded, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (TEXTBOOK_DOC_ID, "space_textbook", "示例教材·有理数的加减运算", "", "md", 8, 0, "ready", db.now_ms()),
        )
    if not db.query_one("SELECT id FROM documents WHERE id=?", (STANDARD_DOC_ID,)):
        db.execute(
            "INSERT INTO documents(id, space_id, name, file_path, file_type, chunk_count, embedded, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (STANDARD_DOC_ID, "space_standard", "课程示例片段", "", "txt", 1, 0, "ready", db.now_ms()),
        )

    try:
        from .services.rag_service import rag_service

        rag_service.reindex_all(only_unembedded=True)
    except Exception as exc:  # 嵌入失败不影响离线演示
        print(f"[Seed] 向量索引初始化跳过: {exc}", file=sys.stderr)
