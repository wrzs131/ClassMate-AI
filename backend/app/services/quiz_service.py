"""随堂测验：真题优先组卷、步骤级批改、掌握度更新与推荐。"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

from .. import agents, db
from ..db import dumps, loads
from ..json_utils import answers_equal
from ..schemas import GradeResult, QuizAnswer
from . import question_bank
from .event_bus import append_event


DIFFICULTY_WEIGHT = {"easy": 0.8, "medium": 1.0, "hard": 1.3}


def _quiz_items(quiz_id: str) -> list[dict]:
    rows = db.query(
        "SELECT qi.id AS quiz_item_id, qi.quiz_id, qi.exam_item_id, qi.ord, qi.points, e.* "
        "FROM quiz_items qi JOIN exam_items e ON e.id=qi.exam_item_id "
        "WHERE qi.quiz_id=? ORDER BY qi.ord",
        (quiz_id,),
    )
    items = []
    for row in rows:
        item = dict(row)
        item["options"] = loads(item.get("options"), [])
        items.append(item)
    return items


def _public_item(item: dict, include_answers: bool) -> dict:
    data = {
        "id": item["quiz_item_id"],
        "exam_item_id": item["exam_item_id"],
        "ord": item["ord"],
        "points": item["points"],
        "kp": item["kp"],
        "qtype": item["qtype"],
        "difficulty": item["difficulty"],
        "stem": item["stem"],
        "options": item["options"],
        "source": item.get("source", ""),
        "source_type": item.get("source_type", ""),
    }
    if include_answers:
        data.update({"answer": item["answer"], "analysis": item.get("analysis", "")})
    return data


def update_mastery(student_id: str, kp: str, correct: bool, difficulty: str) -> float:
    row = db.query_one("SELECT score, attempts FROM mastery WHERE student_id=? AND kp=?", (student_id, kp))
    old_score = float(row["score"]) if row else 0.5
    attempts = int(row["attempts"]) if row else 0
    target = 1.0 if correct else 0.0
    weight = DIFFICULTY_WEIGHT.get(difficulty, 1.0)
    # 难题答对加分更多；难题答错扣分也更多，但限制在 0~1
    delta = (target - old_score) * (0.35 if weight >= 1.0 else 0.25)
    if correct and weight >= 1.3:
        delta *= 1.15
    new_score = max(0.0, min(1.0, old_score + delta))
    db.execute(
        "INSERT INTO mastery(student_id, kp, score, attempts, updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(student_id, kp) DO UPDATE SET score=excluded.score, attempts=excluded.attempts, updated_at=excluded.updated_at",
        (student_id, kp, round(new_score, 4), attempts + 1, db.now_ms()),
    )
    return round(new_score, 4)


def student_mastery(student_id: str) -> list[dict]:
    rows = db.query("SELECT kp, score, attempts, updated_at FROM mastery WHERE student_id=? ORDER BY score", (student_id,))
    return rows


def error_counts(student_id: str) -> dict[str, int]:
    rows = db.query(
        "SELECT error_type, COUNT(*) AS n FROM attempts WHERE student_id=? AND correct=0 AND error_type<>'' GROUP BY error_type",
        (student_id,),
    )
    return {row["error_type"]: int(row["n"]) for row in rows}


class QuizService:
    def create_quiz(self, session_id: str, slide_id: str | None, mode: str = "class", student_id: str = "") -> dict:
        session = db.query_one("SELECT * FROM classroom_sessions WHERE id=?", (session_id,))
        if not session:
            raise ValueError("课堂不存在")
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (session["lesson_id"],))
        if not lesson:
            raise ValueError("课件不存在")
        slides = db.query("SELECT * FROM slides WHERE lesson_id=? ORDER BY ord", (session["lesson_id"],))
        if not slides:
            raise ValueError("课件没有幻灯片")
        if slide_id:
            slide = next((s for s in slides if s["id"] == slide_id), None)
            if not slide:
                raise ValueError("幻灯片不存在")
        else:
            idx = min(int(session["current_slide"]), len(slides) - 1)
            slide = slides[idx]
        kp = slide["kp"]
        mix = {"easy": 2, "medium": 2, "hard": 1}
        items = question_bank.select_for_quiz([kp], mix, total=5)
        if not items:
            raise ValueError("该知识点暂无可用题目")
        quiz_id = f"quiz_{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO quizzes(id, session_id, lesson_id, slide_id, student_id, mode, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (quiz_id, session_id, session["lesson_id"], slide["id"], student_id, mode, "open", db.now_ms()),
        )
        for ord_, item in enumerate(items):
            db.execute(
                "INSERT INTO quiz_items(id, quiz_id, exam_item_id, ord, points) VALUES(?,?,?,?,?)",
                (f"{quiz_id}_{ord_}", quiz_id, item["id"], ord_, 10),
            )
        total_points = sum(10 for _ in items)
        public = self.get_quiz(quiz_id, include_answers=False)
        append_event(
            session_id,
            "quiz_push",
            "teacher",
            {
                "quiz_id": quiz_id,
                "slide_id": slide["id"],
                "slide_title": slide["title"],
                "kp": kp,
                "item_count": len(items),
                "max_score": total_points,
                "difficulty": question_bank.coverage_stats([i["id"] for i in items])["difficulty"],
            },
        )
        return public

    def get_quiz(self, quiz_id: str, include_answers: bool = False) -> dict:
        quiz = db.query_one("SELECT * FROM quizzes WHERE id=?", (quiz_id,))
        if not quiz:
            raise ValueError("测验不存在")
        items = _quiz_items(quiz_id)
        return {
            "id": quiz_id,
            "session_id": quiz["session_id"],
            "lesson_id": quiz["lesson_id"],
            "slide_id": quiz["slide_id"],
            "mode": quiz["mode"],
            "status": quiz["status"],
            "created_at": quiz["created_at"],
            "max_score": sum(item["points"] for item in items),
            "items": [_public_item(item, include_answers) for item in items],
        }

    async def submit(self, quiz_id: str, student_id: str, answers: list[QuizAnswer]) -> dict:
        """交卷：先落一条 grading 记录并立即返回，批改放到后台任务。

        原来 5 题逐题串行调用大模型 + 1 次学情诊断全部塞在一个 HTTP 请求里，
        小程序端会先超时报错（request:fail timeout），而服务端其实还在批改，
        表现为「提交报错，过一会儿报告又能看」。
        """
        quiz = db.query_one("SELECT * FROM quizzes WHERE id=?", (quiz_id,))
        if not quiz:
            raise ValueError("测验不存在")
        items = _quiz_items(quiz_id)
        if not items:
            raise ValueError("该测验没有题目")
        answer_map: dict[str, str] = {}
        for ans in answers:
            answer_map[ans.item_id] = ans.answer
            answer_map[ans.item_id.replace(quiz_id + "_", "")] = ans.answer
        pending = [
            {
                "item_id": item["quiz_item_id"],
                "answer": answer_map.get(item["quiz_item_id"], answer_map.get(item["exam_item_id"], "")),
            }
            for item in items
        ]
        max_score = sum(item["points"] for item in items)
        attempt_id = f"qattempt_{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO quiz_attempts(id, quiz_id, student_id, score, max_score, report, status, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                attempt_id,
                quiz_id,
                student_id,
                0,
                max_score,
                dumps(
                    {
                        "quiz_id": quiz_id,
                        "student_id": student_id,
                        "status": "grading",
                        "max_score": max_score,
                        "item_count": len(items),
                    }
                ),
                "grading",
                db.now_ms(),
            ),
        )
        return {"attempt_id": attempt_id, "max_score": max_score, "answers": pending}

    async def grade_attempt(self, quiz_id: str, attempt_id: str, student_id: str, pending: list[dict]) -> None:
        """后台批改：逐题并行打分（原实现串行，5 题就能把请求拖过 1 分钟）。"""
        try:
            quiz = db.query_one("SELECT * FROM quizzes WHERE id=?", (quiz_id,))
            if not quiz:
                raise ValueError("测验不存在")
            items = _quiz_items(quiz_id)
            answer_map = {row["item_id"]: row["answer"] for row in pending}

            async def grade_one(item: dict) -> GradeResult:
                answer = answer_map.get(item["quiz_item_id"], "")
                try:
                    return await agents.agents.grade(item, answer)
                except Exception:
                    # 单题模型失败时退回确定性判分，避免整份测验永远停在「批改中」
                    ok = answers_equal(item.get("answer", ""), answer)
                    return GradeResult(
                        correct=ok,
                        score=0,
                        error_type="" if ok else "待人工核对",
                        step_feedback=["批改服务暂时不可用，请先对照解析自查。"],
                        explanation=item.get("analysis", ""),
                    )

            grades = await asyncio.gather(*[grade_one(item) for item in items])

            results = []
            score = 0
            max_score = sum(item["points"] for item in items)
            for item, grade in zip(items, grades):
                answer = answer_map.get(item["quiz_item_id"], "")
                points = item["points"] if grade.correct else 0
                score += points
                db.execute(
                    "INSERT INTO attempts(id, quiz_id, quiz_item_id, student_id, answer, correct, error_type, feedback, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        f"attempt_{uuid.uuid4().hex[:10]}",
                        quiz_id,
                        item["quiz_item_id"],
                        student_id,
                        answer,
                        1 if grade.correct else 0,
                        grade.error_type,
                        dumps(grade.model_dump()),
                        db.now_ms(),
                    ),
                )
                mastery = update_mastery(student_id, item["kp"], grade.correct, item["difficulty"])
                results.append(
                    {
                        "quiz_item_id": item["quiz_item_id"],
                        "exam_item_id": item["exam_item_id"],
                        "kp": item["kp"],
                        "stem": item["stem"],
                        "options": item["options"],
                        "answer": item["answer"],
                        "analysis": item.get("analysis", ""),
                        "student_answer": answer,
                        "correct": grade.correct,
                        "points": points,
                        "points_max": item["points"],
                        "error_type": grade.error_type,
                        "step_feedback": grade.step_feedback,
                        "mastery": mastery,
                        "source": item.get("source", ""),
                        "source_type": item.get("source_type", ""),
                    }
                )

            mastery_rows = student_mastery(student_id)
            weak = [row["kp"] for row in mastery_rows if float(row["score"]) < 0.6]
            error_stats = error_counts(student_id)
            wrong_ids = [r["exam_item_id"] for r in results if not r["correct"]]
            weak_kps = list(dict.fromkeys([r["kp"] for r in results if not r["correct"]])) or weak
            recommended = question_bank.recommend_similar(weak_kps, wrong_ids, limit=3)
            diagnosis = await agents.agents.diagnosis(
                student_id,
                [{"kp": row["kp"], "score": row["score"], "attempts": row["attempts"]} for row in mastery_rows],
                weak,
                error_stats,
            )
            report = {
                "quiz_id": quiz_id,
                "student_id": student_id,
                "status": "graded",
                "score": score,
                "max_score": max_score,
                "percent": round(score / max_score * 100, 1) if max_score else 0,
                "items": results,
                "mastery": mastery_rows,
                "weak_points": weak,
                "error_counts": error_stats,
                "diagnosis": diagnosis.model_dump(),
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
                "created_at": db.now_ms(),
            }
            db.execute(
                "UPDATE quiz_attempts SET score=?, max_score=?, report=?, status='graded' WHERE id=?",
                (score, max_score, dumps(report), attempt_id),
            )
            db.execute("UPDATE quizzes SET status='submitted' WHERE id=?", (quiz_id,))
            if quiz["session_id"]:
                append_event(
                    quiz["session_id"],
                    "quiz_submitted",
                    "student",
                    {
                        "quiz_id": quiz_id,
                        "student_id": student_id,
                        "score": score,
                        "max_score": max_score,
                        "percent": report["percent"],
                        "weak_points": weak,
                        "error_counts": error_stats,
                    },
                )
        except Exception as exc:  # 后台任务不能静默失败：落 failed 状态，前端才能给出提示
            db.execute(
                "UPDATE quiz_attempts SET status='failed', report=? WHERE id=?",
                (
                    dumps(
                        {
                            "quiz_id": quiz_id,
                            "student_id": student_id,
                            "status": "failed",
                            "error": f"批改失败：{exc}",
                        }
                    ),
                    attempt_id,
                ),
            )

    def report(self, quiz_id: str, student_id: str) -> dict:
        row = db.query_one(
            "SELECT report, status FROM quiz_attempts WHERE quiz_id=? AND student_id=? ORDER BY created_at DESC LIMIT 1",
            (quiz_id, student_id),
        )
        if not row:
            raise ValueError("还没有提交记录")
        data = loads(row["report"], {})
        data.setdefault("status", row.get("status") or "graded")
        return data

    def quiz_stats(self, quiz_id: str) -> dict:
        attempts = db.query(
            "SELECT * FROM quiz_attempts WHERE quiz_id=? AND status='graded' ORDER BY created_at DESC",
            (quiz_id,),
        )
        reports = [loads(row["report"], {}) for row in attempts]
        n = len(reports)
        avg = round(sum(r.get("percent", 0) for r in reports) / n, 1) if n else 0
        items = _quiz_items(quiz_id)
        per_item = []
        for item in items:
            rows = db.query(
                "SELECT COUNT(*) AS total, SUM(correct) AS correct FROM attempts WHERE quiz_id=? AND quiz_item_id=?",
                (quiz_id, item["quiz_item_id"]),
            )
            stats = rows[0] if rows else {"total": 0, "correct": 0}
            total = int(stats["total"] or 0)
            correct = int(stats["correct"] or 0)
            per_item.append(
                {
                    "quiz_item_id": item["quiz_item_id"],
                    "stem": item["stem"],
                    "kp": item["kp"],
                    "difficulty": item["difficulty"],
                    "correct_rate": round(correct / total * 100, 1) if total else 0,
                    "answered": total,
                }
            )
        return {"attempts": n, "average": avg, "per_item": per_item}

    def dashboard(self, session_id: str) -> dict:
        session = db.query_one("SELECT * FROM classroom_sessions WHERE id=?", (session_id,))
        if not session:
            raise ValueError("课堂不存在")
        members = db.query(
            "SELECT u.id, u.nickname, u.username FROM classroom_members m JOIN users u ON u.id=m.student_id "
            "WHERE m.session_id=? ORDER BY m.joined_at",
            (session_id,),
        )
        quizzes = db.query("SELECT * FROM quizzes WHERE session_id=? ORDER BY created_at DESC", (session_id,))
        attempts = db.query(
            "SELECT qa.*, u.nickname FROM quiz_attempts qa JOIN users u ON u.id=qa.student_id "
            "WHERE qa.status='graded' AND qa.quiz_id IN (SELECT id FROM quizzes WHERE session_id=?) "
            "ORDER BY qa.created_at DESC",
            (session_id,),
        )
        reports = [loads(row["report"], {}) for row in attempts]
        n = len(reports)
        avg = round(sum(r.get("percent", 0) for r in reports) / n, 1) if n else 0
        error_stats: dict[str, int] = {}
        kp_stats: dict[str, list[float]] = {}
        for report in reports:
            for key, value in (report.get("error_counts") or {}).items():
                error_stats[key] = error_stats.get(key, 0) + int(value)
            for row in report.get("mastery", []):
                kp_stats.setdefault(row["kp"], []).append(float(row["score"]))
        kp_mastery = [
            {"kp": kp, "average": round(sum(values) / len(values), 3), "samples": len(values)}
            for kp, values in sorted(kp_stats.items())
        ]
        recent = [
            {
                "student": row.get("nickname", ""),
                "score": row["score"],
                "max_score": row["max_score"],
                "percent": reports[idx].get("percent", 0),
                "created_at": row["created_at"],
            }
            for idx, row in enumerate(attempts[:10])
        ]
        return {
            "session_id": session_id,
            "class_code": session["class_code"],
            "current_slide": session["current_slide"],
            "students": members,
            "student_count": len(members),
            "submissions": n,
            "average": avg,
            "kp_mastery": kp_mastery,
            "error_counts": error_stats,
            "recent": recent,
            "quizzes": [
                {
                    "id": q["id"],
                    "slide_id": q["slide_id"],
                    "status": q["status"],
                    "created_at": q["created_at"],
                    "stats": self.quiz_stats(q["id"]),
                }
                for q in quizzes
            ],
        }


quiz_service = QuizService()
