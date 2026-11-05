"""MCP Server：把教师端可用的增删改查能力注册成 MCP 工具。

参考 backend-example/mcp-agent-service 的 FastMCP 写法：工具直接返回 JSON 字符串，
模型（硅基流动 Qwen）通过 OpenAI function calling 选择工具，由 agent.py 执行。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastmcp import FastMCP

from . import db
from .schemas import SlidePatch
from .services import question_bank
from .services.classroom_service import classroom_service
from .services.courseware_service import courseware_service
from .services.diagnosis_service import diagnosis_service
from .services.rag_service import rag_service

mcp = FastMCP(
    name="classmate-ai",
    instructions=(
        "ClassMate AI 课堂助教平台的教师端工具。"
        "所有 id 必须来自工具查询结果，禁止编造；删除类工具由系统要求教师二次确认。"
    ),
)

# 写操作（需要模型显式调用）与删除操作（需要教师二次确认）
WRITE_TOOLS = {
    "create_knowledge_space",
    "import_exam_items",
    "update_slide",
    "create_classroom",
    "close_classroom",
}
DESTRUCTIVE_TOOLS = {"delete_exam_item", "delete_document", "delete_lesson"}

TOOL_LABELS = {
    "search_knowledge": "检索教材/真题",
    "list_exam_items": "查询题库",
    "list_lessons": "查询课件",
    "get_lesson": "查看课件详情",
    "list_classrooms": "查询课堂",
    "get_class_dashboard": "查看课堂看板",
    "get_class_report": "查看班级学情",
    "get_student_diagnosis": "查看学生画像",
    "create_knowledge_space": "新建知识空间",
    "import_exam_items": "导入真题",
    "update_slide": "修改课件页",
    "create_classroom": "开课",
    "close_classroom": "关闭课堂",
    "delete_exam_item": "删除题目",
    "delete_document": "删除知识库文档",
    "delete_lesson": "删除课件",
}


CST = timezone(timedelta(hours=8))


def _fmt_ts(ms: float) -> str:
    """把毫秒时间戳格式化为北京时间字符串，避免模型自己换算日期时算错。"""
    return datetime.fromtimestamp(ms / 1000, CST).strftime("%Y-%m-%d %H:%M")


def _humanize(value: Any) -> Any:
    """递归把 created_at / updated_at 等毫秒时间戳转成可读时间。"""
    if isinstance(value, dict):
        return {
            key: _fmt_ts(item) if key.endswith("_at") and isinstance(item, (int, float)) and item > 1e11 else _humanize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_humanize(item) for item in value]
    return value


def _ok(data: Any = None, message: str = "") -> str:
    return json.dumps(
        {"ok": True, "data": _humanize(data), "message": message}, ensure_ascii=False, default=str
    )


def _err(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


# ---------------------------------------------------------------- 查询类


@mcp.tool
def search_knowledge(query: str, kind: str = "", top_k: int = 5) -> str:
    """在教材库 / 真题库中做语义检索，返回命中的片段与来源。

    Args:
        query: 检索关键词，例如“异号相加 绝对值”。
        kind: 可选，textbook 只搜教材，exam 只搜真题；留空表示全部。
        top_k: 返回条数，默认 5。
    """
    if not query.strip():
        return _err("检索词不能为空")
    kind_value = kind.strip() or None
    hits = rag_service.search(query, None, kind_value, None, max(1, min(int(top_k), 10)))
    return _ok(
        [
            {
                "chunk_id": item.get("chunk_id"),
                "source": item.get("source"),
                "kind": item.get("kind"),
                "score": item.get("score"),
                "content": (item.get("content") or "")[:240],
            }
            for item in hits
        ],
        f"命中 {len(hits)} 条片段",
    )


@mcp.tool
def list_exam_items(kp: str = "", difficulty: str = "", limit: int = 20) -> str:
    """查询题库中的真题 / 教材改编题，返回 id、知识点、难度、题干、答案与来源。

    Args:
        kp: 可选，知识点关键词，例如“有理数的加法”。
        difficulty: 可选，easy / medium / hard。
        limit: 返回条数，默认 20，最大 50。
    """
    items = question_bank.list_items(
        kp=kp.strip() or None,
        difficulty=difficulty.strip() or None,
        limit=max(1, min(int(limit), 50)),
    )
    return _ok(
        [
            {
                "id": item["id"],
                "kp": item.get("kp"),
                "difficulty": item.get("difficulty"),
                "qtype": item.get("qtype"),
                "stem": item.get("stem"),
                "answer": item.get("answer"),
                "source_type": item.get("source_type"),
            }
            for item in items
        ],
        f"共 {len(items)} 道题",
    )


@mcp.tool
def list_lessons() -> str:
    """查询所有课件，返回 id、标题、章节、创建时间。"""
    lessons = courseware_service.list_lessons()
    return _ok(
        [
            {
                "id": item["id"],
                "title": item.get("title"),
                "chapter": item.get("chapter"),
                "grade": item.get("grade"),
                "created_at": item.get("created_at"),
            }
            for item in lessons
        ],
        f"共 {len(lessons)} 份课件",
    )


@mcp.tool
def get_lesson(lesson_id: str) -> str:
    """查询一份课件的详情，包含每一页的 id、标题与要点，用于定位要修改的幻灯片。

    Args:
        lesson_id: 课件 id，必须来自 list_lessons 的结果。
    """
    try:
        lesson = courseware_service.get_lesson(lesson_id)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(
        {
            "id": lesson["id"],
            "title": lesson.get("title"),
            "slides": [
                {"id": slide["id"], "ord": slide.get("ord"), "title": slide.get("title"), "bullets": slide.get("bullets")}
                for slide in lesson.get("slides", [])
            ],
        }
    )


@mcp.tool
def list_classrooms(teacher_id: str = "") -> str:
    """查询课堂（含进行中与历史），返回 id、课堂码、状态、课件标题。

    Args:
        teacher_id: 由系统自动填充，模型无需填写。
    """
    sessions = classroom_service.list_sessions(teacher_id) if teacher_id else []
    return _ok(
        [
            {
                "id": item["id"],
                "class_code": item.get("class_code"),
                "status": item.get("status"),
                "lesson_title": item.get("lesson_title"),
                "created_at": item.get("created_at"),
            }
            for item in sessions
        ],
        f"共 {len(sessions)} 堂课堂",
    )


@mcp.tool
def get_class_dashboard(session_id: str) -> str:
    """查看某一堂课的看板：学生数、提交人数、平均得分率、知识点掌握与错因分布。

    Args:
        session_id: 课堂 id，必须来自 list_classrooms 的结果。
    """
    try:
        return _ok(classroom_service.dashboard(session_id))
    except ValueError as exc:
        return _err(str(exc))


@mcp.tool
def get_class_report(session_id: str) -> str:
    """查看某一堂课的班级学情诊断报告。

    Args:
        session_id: 课堂 id，必须来自 list_classrooms 的结果。
    """
    try:
        return _ok(diagnosis_service.class_report(session_id))
    except ValueError as exc:
        return _err(str(exc))


@mcp.tool
def get_student_diagnosis(student: str) -> str:
    """查看某个学生的学情画像（薄弱知识点、错因、掌握度）。

    Args:
        student: 学生 id / 账号 / 昵称，例如“小明”。
    """
    key = student.strip()
    if not key:
        return _err("请提供学生 id、账号或昵称")
    row = db.query_one(
        "SELECT id, nickname, role FROM users WHERE id=? OR username=? OR nickname=? LIMIT 1",
        (key, key, key),
    )
    if not row or row.get("role") != "student":
        return _err(f"没有找到学生「{key}」")
    return _ok({"student": row["nickname"], **diagnosis_service.student_report(row["id"])})


# ---------------------------------------------------------------- 写入类


@mcp.tool
def create_knowledge_space(
    name: str,
    kind: str = "textbook",
    subject: str = "数学",
    grade: str = "七年级",
    textbook_version: str = "北师大版（2026）",
    description: str = "",
) -> str:
    """新建一个知识空间（教材库 / 真题库）。

    Args:
        name: 空间名称，例如“八年级几何真题库”。
        kind: textbook 教材库 / exam 真题库。
        subject / grade / textbook_version: 学科、年级、教材版本。
        description: 可选描述。
    """
    if not name.strip():
        return _err("空间名称不能为空")
    kind_value = kind.strip() or "textbook"
    if kind_value not in {"textbook", "exam"}:
        return _err("kind 只能是 textbook 或 exam")
    space = rag_service.create_space(
        kind_value, name.strip(), subject.strip(), grade.strip(), textbook_version.strip(), description.strip()
    )
    return _ok(space, f"已创建空间「{space.get('name')}」")


@mcp.tool
def import_exam_items(space_id: str, items: list[dict]) -> str:
    """向真题库批量导入题目（结构化数据）。

    Args:
        space_id: 目标知识空间 id，必须来自 create_knowledge_space 或 list_classrooms 之外的查询结果。
        items: 题目列表，每项至少包含 kp、stem、answer；可选 qtype、difficulty、options、analysis、source。
    """
    space = rag_service.get_space(space_id)
    if not space:
        return _err("知识空间不存在")
    if not items:
        return _err("题目列表为空")
    try:
        ids = rag_service.import_exams(space_id, items)
    except Exception as exc:  # 缺字段 / 类型不对时给出可读提示
        return _err(f"导入失败：{exc}")
    return _ok({"imported": len(ids), "ids": ids}, f"已导入 {len(ids)} 道题")


@mcp.tool
def update_slide(
    lesson_id: str,
    slide_id: str,
    title: Optional[str] = None,
    bullets: Optional[list[str]] = None,
) -> str:
    """修改某一份课件的某一页（标题 / 要点）。

    Args:
        lesson_id: 课件 id，必须来自 list_lessons 的结果。
        slide_id: 幻灯片 id，可从课件详情或 list_lessons 之后的工具结果中获得。
        title: 新标题，留空表示不修改。
        bullets: 新要点列表，留空表示不修改。
    """
    try:
        patch = SlidePatch(title=title, bullets=bullets)
        slide = courseware_service.update_slide(lesson_id, slide_id, patch)
    except ValueError as exc:
        return _err(str(exc))
    return _ok({"id": slide.get("id"), "title": slide.get("title")}, "课件页已更新")


@mcp.tool
def create_classroom(lesson_id: str, teacher_id: str = "") -> str:
    """用指定课件开一堂课，返回课堂 id 与 6 位课堂码。

    Args:
        lesson_id: 课件 id，必须来自 list_lessons 的结果。
        teacher_id: 由系统自动填充，模型无需填写。
    """
    if not teacher_id:
        return _err("缺少教师身份，无法开课")
    try:
        state = classroom_service.create_session(lesson_id, teacher_id)
    except ValueError as exc:
        return _err(str(exc))
    session = state.get("session", {})
    return _ok(
        {"id": session.get("id"), "class_code": session.get("class_code"), "lesson_title": session.get("lesson_title")},
        f"已开课，课堂码 {session.get('class_code')}",
    )


@mcp.tool
def close_classroom(session_id: str, teacher_id: str = "") -> str:
    """关闭一堂课，关闭后课堂码失效。

    Args:
        session_id: 课堂 id，必须来自 list_classrooms 的结果。
        teacher_id: 由系统自动填充，模型无需填写。
    """
    if not teacher_id:
        return _err("缺少教师身份，无法关闭课堂")
    try:
        session = classroom_service.close_session(session_id, teacher_id)
    except ValueError as exc:
        return _err(str(exc))
    return _ok({"id": session.get("id"), "status": session.get("status")}, "课堂已关闭")


# ---------------------------------------------------------------- 删除类（需二次确认）


@mcp.tool
def delete_exam_item(exam_item_id: str) -> str:
    """删除题库中的一道题。若该题已被随堂测验引用则拒绝删除。

    Args:
        exam_item_id: 题目 id，必须来自 list_exam_items 的结果。
    """
    try:
        item = question_bank.delete_item(exam_item_id)
    except ValueError as exc:
        return _err(str(exc))
    return _ok({"id": item.get("id"), "stem": item.get("stem")}, "题目已删除")


@mcp.tool
def delete_document(document_id: str) -> str:
    """删除知识库中的一份文档及其全部分块。

    Args:
        document_id: 文档 id，必须来自知识库查询结果。
    """
    try:
        doc = rag_service.delete_document(document_id)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(doc, f"已删除文档「{doc.get('name')}」")


@mcp.tool
def delete_lesson(lesson_id: str) -> str:
    """删除一份课件；若该课件已用于课堂则拒绝删除。

    Args:
        lesson_id: 课件 id，必须来自 list_lessons 的结果。
    """
    try:
        lesson = courseware_service.delete_lesson(lesson_id)
    except ValueError as exc:
        return _err(str(exc))
    return _ok(lesson, f"已删除课件「{lesson.get('title')}」")
