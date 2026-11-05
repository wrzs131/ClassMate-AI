"""学情诊断聚合。"""
from __future__ import annotations

from .. import db
from ..db import loads
from . import question_bank
from .quiz_service import error_counts, student_mastery


class DiagnosisService:
    def student_report(self, student_id: str) -> dict:
        user = db.query_one("SELECT id, nickname, username FROM users WHERE id=?", (student_id,))
        mastery = student_mastery(student_id)
        weak = [row["kp"] for row in mastery if float(row["score"]) < 0.6]
        errors = error_counts(student_id)
        attempts = db.query(
            "SELECT a.*, e.stem, e.kp, e.difficulty, e.source_type FROM attempts a "
            "JOIN exam_items e ON e.id=(SELECT exam_item_id FROM quiz_items WHERE id=a.quiz_item_id) "
            "WHERE a.student_id=? ORDER BY a.created_at DESC LIMIT 20",
            (student_id,),
        )
        recommended = question_bank.recommend_similar(weak, [], limit=5) if weak else []
        return {
            "student": user or {"id": student_id},
            "mastery": mastery,
            "weak_points": weak,
            "error_counts": errors,
            "attempts": attempts,
            "recommended": [
                {
                    "id": item["id"],
                    "stem": item["stem"],
                    "difficulty": item["difficulty"],
                    "kp": item["kp"],
                    "source": item.get("source", ""),
                    "source_type": item.get("source_type", ""),
                }
                for item in recommended
            ],
            "summary": (
                f"当前最需要补的是：{'、'.join(weak)}。建议先回看对应幻灯片的“生活类比 + 分步推导”，再做 3 道同知识点基础题。"
                if weak
                else "当前掌握较稳，建议继续做中等难度综合题，并保持每天 10 分钟的计算练习。"
            ),
        }

    def class_report(self, session_id: str) -> dict:
        from .quiz_service import quiz_service

        return quiz_service.dashboard(session_id)

    def history(self, quiz_id: str, student_id: str) -> dict:
        rows = db.query(
            "SELECT * FROM quiz_attempts WHERE quiz_id=? AND student_id=? AND status='graded' ORDER BY created_at",
            (quiz_id, student_id),
        )
        for row in rows:
            row["report"] = loads(row.get("report"), {})
        return {"attempts": rows}


diagnosis_service = DiagnosisService()
