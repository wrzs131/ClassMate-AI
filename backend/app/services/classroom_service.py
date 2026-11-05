"""课堂会话、多智能体推进、答疑、总结与实时事件。"""
from __future__ import annotations

import asyncio
import json
import secrets
from typing import AsyncIterator

from .. import agents, db
from ..db import dumps, loads
from ..llm import llm
from . import question_bank
from .event_bus import append_event, list_events
from .quiz_service import quiz_service, student_mastery
from .rag_service import rag_service


def _slide_row(row: dict, include_answers: bool) -> dict:
    slide = dict(row)
    slide["bullets"] = loads(slide.get("bullets"), [])
    slide["script"] = loads(slide.get("script"), {})
    anchor_ids = loads(slide.get("exam_anchor_ids"), [])
    slide["exam_anchor_ids"] = anchor_ids
    slide["exam_anchors"] = question_bank.get_items(anchor_ids, include_answer=include_answers)
    return slide


def _session(session_id: str) -> dict:
    row = db.query_one("SELECT * FROM classroom_sessions WHERE id=?", (session_id,))
    if not row:
        raise ValueError("课堂不存在")
    return row


class ClassroomService:
    def _new_code(self) -> str:
        for _ in range(20):
            code = f"{secrets.randbelow(900000) + 100000}"
            if not db.query_one("SELECT id FROM classroom_sessions WHERE class_code=? AND status='active'", (code,)):
                return code
        raise RuntimeError("课堂码生成失败，请重试")

    def create_session(self, lesson_id: str, teacher_id: str) -> dict:
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
        if not lesson:
            raise ValueError("课件不存在")
        session_id = f"class_{secrets.token_hex(8)}"
        code = self._new_code()
        db.execute(
            "INSERT INTO classroom_sessions(id, lesson_id, teacher_id, class_code, status, current_slide, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (session_id, lesson_id, teacher_id, code, "active", 0, db.now_ms()),
        )
        append_event(
            session_id,
            "class_started",
            "system",
            {"class_code": code, "lesson_id": lesson_id, "lesson_title": lesson["title"]},
        )
        return self.state(session_id, {"id": teacher_id, "role": "teacher"}, 0)

    def join(self, class_code: str, student_id: str) -> dict:
        session = db.query_one(
            "SELECT * FROM classroom_sessions WHERE class_code=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (class_code.strip(),),
        )
        if not session:
            raise ValueError("课堂码无效或课堂已结束")
        existing = db.query_one(
            "SELECT 1 FROM classroom_members WHERE session_id=? AND student_id=?", (session["id"], student_id)
        )
        if not existing:
            db.execute(
                "INSERT INTO classroom_members(session_id, student_id, joined_at) VALUES(?,?,?)",
                (session["id"], student_id, db.now_ms()),
            )
            student = db.query_one("SELECT nickname FROM users WHERE id=?", (student_id,))
            append_event(
                session["id"],
                "student_joined",
                "system",
                {"student_id": student_id, "nickname": student["nickname"] if student else "学生"},
            )
        return self.state(session["id"], {"id": student_id, "role": "student"}, 0)

    def leave(self, session_id: str, student_id: str) -> dict:
        """学生退出课堂：移除成员关系并广播 student_left，教师端人数/成员列表/事件流同步更新。"""
        _session(session_id)
        member = db.query_one(
            "SELECT 1 FROM classroom_members WHERE session_id=? AND student_id=?", (session_id, student_id)
        )
        if not member:
            return {"left": False, "session_id": session_id}
        student = db.query_one("SELECT nickname FROM users WHERE id=?", (student_id,))
        db.execute("DELETE FROM classroom_members WHERE session_id=? AND student_id=?", (session_id, student_id))
        append_event(
            session_id,
            "student_left",
            "system",
            {"student_id": student_id, "nickname": student["nickname"] if student else "学生"},
        )
        return {"left": True, "session_id": session_id}

    def list_sessions(self, teacher_id: str) -> list[dict]:
        rows = db.query(
            "SELECT s.*, l.title AS lesson_title FROM classroom_sessions s JOIN lessons l ON l.id=s.lesson_id "
            "WHERE s.teacher_id=? ORDER BY s.created_at DESC",
            (teacher_id,),
        )
        return rows

    def state(self, session_id: str, user: dict, after_seq: int = 0) -> dict:
        session = _session(session_id)
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (session["lesson_id"],))
        if not lesson:
            raise ValueError("课件不存在")
        include_answers = user.get("role") == "teacher"
        slides = db.query("SELECT * FROM slides WHERE lesson_id=? ORDER BY ord", (session["lesson_id"],))
        current_idx = min(max(0, int(session["current_slide"])), max(0, len(slides) - 1))
        current = _slide_row(slides[current_idx], include_answers) if slides else None
        members = db.query(
            "SELECT u.id, u.nickname, u.username, m.joined_at FROM classroom_members m "
            "JOIN users u ON u.id=m.student_id WHERE m.session_id=? ORDER BY m.joined_at",
            (session_id,),
        )
        latest_quiz = db.query_one(
            "SELECT * FROM quizzes WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,)
        )
        submitted = False
        if latest_quiz and user.get("role") == "student":
            submitted = bool(
                db.query_one(
                    "SELECT 1 FROM quiz_attempts WHERE quiz_id=? AND student_id=?",
                    (latest_quiz["id"], user["id"]),
                )
            )
        return {
            "session": {
                "id": session["id"],
                "class_code": session["class_code"],
                "status": session["status"],
                "current_slide": current_idx,
                "slide_count": len(slides),
            },
            "lesson": {
                "id": lesson["id"],
                "title": lesson["title"],
                "objectives": loads(lesson.get("objectives"), []),
                "chapter": lesson.get("chapter", ""),
                "grade": lesson.get("grade", ""),
                "subject": lesson.get("subject", ""),
            },
            "current_slide": current,
            "students": members,
            "latest_quiz": latest_quiz,
            "quiz_submitted": submitted,
            "events": list_events(session_id, after_seq=after_seq, limit=120),
        }

    async def advance(self, session_id: str, teacher_id: str, include_quiz: bool = False) -> dict:
        session = _session(session_id)
        if session["teacher_id"] != teacher_id:
            raise PermissionError("只有开课教师可以推进课堂")
        if session["status"] == "closed":
            raise ValueError("课堂已关闭，请先开启新的课堂")
        slides = db.query("SELECT * FROM slides WHERE lesson_id=? ORDER BY ord", (session["lesson_id"],))
        if not slides:
            raise ValueError("课件没有幻灯片")
        idx = int(session["current_slide"])
        if idx >= len(slides):
            text = await self.summary(session_id, teacher_id)
            return {"done": True, "summary": text, "state": self.state(session_id, {"id": teacher_id, "role": "teacher"}, 0)}

        slide_row = slides[idx]
        slide = _slide_row(slide_row, True)
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (session["lesson_id"],))
        contexts = rag_service.search(
            f"{slide['title']} {slide['kp']} 有理数 加减 符号",
            kind="textbook",
            top_k=4,
        )
        anchors = slide.get("exam_anchors", [])
        script = slide.get("script", {})
        if not script.get("analogy"):
            script_model = await agents.agents.teacher_script(slide, contexts, anchors[0] if anchors else None)
            script = script_model.model_dump()
            db.execute("UPDATE slides SET script=? WHERE id=?", (dumps(script), slide["id"]))

        append_event(
            session_id,
            "slide_start",
            "system",
            {
                "slide_id": slide["id"],
                "index": idx,
                "total": len(slides),
                "title": slide["title"],
                "bullets": slide["bullets"],
                "kp": slide["kp"],
            },
        )
        append_event(
            session_id,
            "teacher_speak",
            "teacher",
            {
                "slide_id": slide["id"],
                "title": slide["title"],
                "script": script,
                "citations": [
                    {"chunk_id": c["chunk_id"], "source": c.get("source", ""), "score": c.get("score", 0)}
                    for c in contexts
                ],
            },
        )
        questions = await agents.agents.student_questions(slide, anchors)
        append_event(
            session_id,
            "student_questions",
            "student",
            {
                "slide_id": slide["id"],
                "questions": [q.model_dump() for q in questions],
            },
        )
        if questions:
            reply = await agents.agents.assistant_reply(slide, questions[0].question, 1)
            append_event(
                session_id,
                "assistant_answer",
                "assistant",
                {
                    "slide_id": slide["id"],
                    "question": questions[0].question,
                    "reply": reply.model_dump(),
                },
            )

        if include_quiz:
            quiz_service.create_quiz(session_id, slide["id"], mode="class")

        db.execute(
            "UPDATE classroom_sessions SET current_slide=? WHERE id=?",
            (min(idx + 1, len(slides)), session_id),
        )
        return {
            "done": False,
            "slide_index": idx,
            "state": self.state(session_id, {"id": teacher_id, "role": "teacher"}, 0),
        }

    async def ask(self, session_id: str, student_id: str, question: str, image_base64: str | None = None) -> dict:
        session = _session(session_id)
        slides = db.query("SELECT * FROM slides WHERE lesson_id=? ORDER BY ord", (session["lesson_id"],))
        if not slides:
            raise ValueError("课件没有幻灯片")
        idx = min(int(session["current_slide"]), len(slides) - 1)
        slide = _slide_row(slides[idx], False)
        previous = db.query_one(
            "SELECT COUNT(*) AS n FROM qa_turns WHERE session_id=? AND student_id=? AND created_at>(?)",
            (session_id, student_id, session["created_at"]),
        )
        hint_level = min(3, int(previous["n"]) if previous else 0)
        student = db.query_one("SELECT nickname FROM users WHERE id=?", (student_id,))
        image_note = ""
        if image_base64 and llm.available:
            identified = await llm.chat(
                "你是课堂助教。请只识别图片中的题目内容和学生的手写步骤，指出学生可能卡住的地方；不要直接给出最终答案。",
                (question or "请识别这张图片中的数学题和我的写法。"),
                image_base64=image_base64,
            )
            if identified:
                image_note = f"\n[图片识别] {identified[:600]}"
        effective_question = (question.strip() if question else "请老师看看我拍的这道题。") + image_note
        reply = await agents.agents.assistant_reply(slide, effective_question, hint_level)
        qa_id = f"qa_{secrets.token_hex(8)}"
        db.execute(
            "INSERT INTO qa_turns(id, session_id, student_id, question, image_path, hint_level, reply, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (qa_id, session_id, student_id, effective_question, "uploaded" if image_base64 else "", hint_level, dumps(reply.model_dump()), db.now_ms()),
        )
        append_event(
            session_id,
            "student_question",
            "student",
            {
                "qa_id": qa_id,
                "student_id": student_id,
                "nickname": student["nickname"] if student else "学生",
                "question": effective_question,
                "has_image": bool(image_base64),
                "hint_level": hint_level,
            },
        )
        append_event(
            session_id,
            "assistant_answer",
            "assistant",
            {
                "qa_id": qa_id,
                "student_id": student_id,
                "nickname": student["nickname"] if student else "学生",
                "question": effective_question,
                "reply": reply.model_dump(),
            },
        )
        return {
            "qa_id": qa_id,
            "hint_level": hint_level,
            "reply": reply.model_dump(),
            "slide_title": slide["title"],
        }

    async def summary(self, session_id: str, teacher_id: str) -> str:
        session = _session(session_id)
        if session["teacher_id"] != teacher_id:
            raise PermissionError("只有开课教师可以生成总结")
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (session["lesson_id"],))
        slides = db.query("SELECT id FROM slides WHERE lesson_id=? ORDER BY ord", (session["lesson_id"],))
        questions = [
            row["question"]
            for row in db.query(
                "SELECT question FROM qa_turns WHERE session_id=? ORDER BY created_at DESC LIMIT 8", (session_id,)
            )
        ]
        members = db.query("SELECT student_id FROM classroom_members WHERE session_id=?", (session_id,))
        weak: list[str] = []
        for member in members:
            weak.extend([row["kp"] for row in student_mastery(member["student_id"]) if float(row["score"]) < 0.6])
        weak = list(dict.fromkeys(weak))
        text = await agents.agents.summary(lesson or {}, len(slides), questions, weak)
        payload = {"text": text, "weak_points": weak, "question_count": len(questions)}
        append_event(session_id, "summary", "teacher", payload)
        db.execute("UPDATE classroom_sessions SET status='finished' WHERE id=?", (session_id,))
        return text

    def close_session(self, session_id: str, teacher_id: str) -> dict:
        """关闭（归档）当前课堂：关闭后课堂码失效，教师可重新开课生成新的课堂码。"""
        session = _session(session_id)
        if session["teacher_id"] != teacher_id:
            raise PermissionError("只有开课教师可以关闭课堂")
        if session["status"] == "closed":
            return {"session_id": session_id, "status": "closed", "already_closed": True}
        db.execute("UPDATE classroom_sessions SET status='closed' WHERE id=?", (session_id,))
        append_event(
            session_id,
            "class_closed",
            "teacher",
            {"class_code": session["class_code"], "previous_status": session["status"]},
        )
        return {"session_id": session_id, "status": "closed", "already_closed": False}

    async def event_stream(self, session_id: str, after_seq: int = 0, max_seconds: int = 1800) -> AsyncIterator[str]:
        current = after_seq
        waited = 0
        while waited < max_seconds:
            events = list_events(session_id, after_seq=current, limit=50)
            for event in events:
                current = int(event["seq"])
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if not events:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)
            waited += 1

    def dashboard(self, session_id: str) -> dict:
        return quiz_service.dashboard(session_id)


classroom_service = ClassroomService()
