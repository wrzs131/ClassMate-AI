"""备课：基于教材检索 + 参考试卷生成课件，并保证题目可溯源、难度有分层。"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from pptx import Presentation
from pptx.util import Inches, Pt

from .. import agents, db
from ..config import EXPORT_DIR
from ..db import dumps, loads
from ..llm import llm
from ..schemas import CoursewareDraft, CoursewareSlide, SlidePatch, SlideScript
from . import question_bank
from .rag_service import rag_service


CURATED_SLIDES: list[dict[str, Any]] = [
    {
        "title": "从生活账本走进有理数加法",
        "kp": "有理数的概念",
        "bullets": [
            "收入、向东、上升记为正；支出、向西、下降记为负",
            "正负数不是“好坏”，而是表示方向相反的量",
            "把几笔收支合并，就是有理数的加法",
        ],
        "candidates": ["ref_q2", "ref_q1", "ref_q17"],
    },
    {
        "title": "同号相加：同向就把力量叠加",
        "kp": "有理数的加法",
        "bullets": [
            "同号两数相加，符号不变",
            "把两个数的绝对值相加",
            "例：(-7)+(-5)=-12；(-1/2)+(-1/3)+(-1/6)=-1",
        ],
        "candidates": ["sample_add_same_1", "sample_add_same_2", "sample_add_hard", "sample_add_zero"],
    },
    {
        "title": "异号相加：先抵消，再看谁更大",
        "kp": "有理数的加法",
        "bullets": [
            "异号相加，取绝对值较大的数的符号",
            "用较大的绝对值减去较小的绝对值",
            "绝对值相等时和为 0；例：(-8)+3=-5，15+(-9)=6",
        ],
        "candidates": ["ref_q4", "sample_add_diff_1", "sample_add_diff_2", "sample_sign", "ref_q14"],
    },
    {
        "title": "相反数与 0：回到原点的智慧",
        "kp": "相反数与倒数",
        "bullets": [
            "互为相反数的两个数相加得 0：a+(-a)=0",
            "任何数与 0 相加仍得这个数",
            "相反数是“和为 0”，倒数是“积为 1”，不要混淆",
        ],
        "candidates": ["ref_q21", "sample_opposite", "ref_q1"],
    },
    {
        "title": "减法转加法：减去一个数等于加相反数",
        "kp": "有理数的减法",
        "bullets": [
            "a-b=a+(-b)",
            "减号变加号的同时，减数要变成相反数",
            "例：5-(-7)=12；-3-4=-7；0-(-6)=6",
        ],
        "candidates": ["ref_q18_1", "sample_sub_1", "sample_sub_2", "sample_sub_hard", "sample_sub_5"],
    },
    {
        "title": "加减混合：统一成加法，凑整更简单",
        "kp": "有理数加减混合运算",
        "bullets": [
            "把加减混合运算统一成加法",
            "省略加号与括号，写成代数和",
            "利用交换律、结合律把相反数或凑整的数分组",
        ],
        "candidates": ["ref_q20", "sample_mix_1", "sample_mix_2", "ref_q18_3", "sample_series", "sample_fraction_hard"],
    },
    {
        "title": "真题演练：从会算到会用",
        "kp": "有理数加减应用",
        "bullets": [
            "先圈出正方向，把文字转成带符号的算式",
            "计算后回到情境回答“方向/结余/温度”",
            "分层练习：直接计算 → 数轴距离 → 实际应用",
        ],
        "candidates": ["ref_q22", "ref_q23", "sample_word_temp", "sample_word_bank", "ref_q20", "ref_q16"],
    },
]


def _lesson_objectives(chapter: str) -> list[str]:
    return [
        f"理解{chapter}的算理，能说出同号、异号与减法的符号规则",
        "能熟练进行有理数的加法、减法与加减混合运算",
        "能用生活类比解释符号规则，并指出常见易错点",
        "能借助参考试卷题完成从“会算”到“会用”的迁移",
    ]


def _pick_anchors(pool: dict[str, dict], exam_count: int) -> dict[int, list[str]]:
    exam_count = max(6, min(14, exam_count))
    per_slide: dict[int, list[str]] = {i: [] for i in range(len(CURATED_SLIDES))}
    chosen: list[str] = []

    def add(idx: int, item_id: str) -> bool:
        if item_id not in pool or item_id in chosen:
            return False
        per_slide[idx].append(item_id)
        chosen.append(item_id)
        return True

    # 第一轮：每张幻灯片至少一道可溯源题
    for idx, slide in enumerate(CURATED_SLIDES):
        for item_id in slide["candidates"]:
            if add(idx, item_id):
                break
    # 第二轮：优先参考试卷题，再按难度补足
    references = [i for i in pool if pool[i].get("source_type") == "reference_paper"]
    others = [i for i in pool if i not in references]
    extras = references + others
    while len(chosen) < exam_count:
        progressed = False
        for item_id in extras:
            for idx in range(len(CURATED_SLIDES)):
                if len(chosen) >= exam_count:
                    break
                if item_id in CURATED_SLIDES[idx]["candidates"] and add(idx, item_id):
                    progressed = True
                    break
            if len(chosen) >= exam_count:
                break
        if not progressed:
            break
    # 难度兜底：确保至少各有一道易/中/难
    for difficulty in ("easy", "medium", "hard"):
        if not any(pool[i]["difficulty"] == difficulty for i in chosen):
            for idx, slide in enumerate(CURATED_SLIDES):
                for item_id in slide["candidates"]:
                    if item_id in pool and pool[item_id]["difficulty"] == difficulty:
                        add(idx, item_id)
                        break
                else:
                    continue
                break
    return per_slide


def _fallback_draft(params: dict, pool: dict[str, dict], exam_count: int) -> CoursewareDraft:
    per_slide = _pick_anchors(pool, exam_count)
    slides: list[CoursewareSlide] = []
    for idx, slide in enumerate(CURATED_SLIDES):
        anchors = per_slide.get(idx, [])
        first_exam = pool.get(anchors[0]) if anchors else None
        script = agents.fallback_script(slide["title"], slide["kp"], first_exam)
        slides.append(
            CoursewareSlide(
                title=slide["title"],
                bullets=slide["bullets"],
                kp=slide["kp"],
                script=script,
                exam_anchor_ids=anchors,
            )
        )
    title = params.get("lesson_title") or f"{params.get('chapter', '有理数的加减运算')}·互动课堂"
    return CoursewareDraft(title=title, objectives=_lesson_objectives(params.get("chapter", "有理数的加减运算")), slides=slides)


def _balance_difficulties(
    slides: list[CoursewareSlide], pool: dict[str, dict], selected: list[str], exam_count: int
) -> list[str]:
    """模型容易只挑简单题：这里在代码层兜底难度配比，保证每份课件都有易/中/难。"""
    minimum = {"easy": 2, "medium": 2, "hard": 1}
    chosen = set(selected)

    def count(difficulty: str) -> int:
        return sum(1 for item_id in chosen if pool[item_id].get("difficulty") == difficulty)

    for difficulty, need in minimum.items():
        while count(difficulty) < need:
            candidates = sorted(
                [i for i in pool if i not in chosen and pool[i].get("difficulty") == difficulty],
                key=lambda i: 0 if pool[i].get("source_type") == "reference_paper" else 1,
            )
            if not candidates:
                break
            item_id = candidates[0]
            target = next((s for s in slides if s.kp == pool[item_id].get("kp")), None)
            if target is None:
                target = min(slides, key=lambda s: len(s.exam_anchor_ids))
            # 题量已达上限时，替换一条难度已超配的锚点，避免无限追加
            if len(chosen) >= exam_count:
                victim = next(
                    (
                        i
                        for s in slides
                        if len(s.exam_anchor_ids) >= 2
                        for i in s.exam_anchor_ids
                        if pool[i].get("difficulty") != difficulty
                        and count(pool[i].get("difficulty", "")) > minimum.get(pool[i].get("difficulty"), 0)
                    ),
                    None,
                )
                if victim:
                    for s in slides:
                        if victim in s.exam_anchor_ids:
                            s.exam_anchor_ids.remove(victim)
                            break
                    chosen.discard(victim)
                    if victim in selected:
                        selected.remove(victim)
            target.exam_anchor_ids.append(item_id)
            chosen.add(item_id)
            selected.append(item_id)
    return selected


def _normalize_llm_draft(
    draft: CoursewareDraft, params: dict, pool: dict[str, dict], exam_count: int
) -> Optional[CoursewareDraft]:
    if len(draft.slides) < 5:
        return None
    valid = [s for s in draft.slides if s.title and s.bullets]
    if len(valid) < 5:
        return None
    selected: list[str] = []
    for slide in valid:
        slide.exam_anchor_ids = list(dict.fromkeys(i for i in slide.exam_anchor_ids if i in pool))
        if not slide.exam_anchor_ids:
            # 用精选候选补一道
            for curated in CURATED_SLIDES:
                if curated["kp"] == slide.kp:
                    for item_id in curated["candidates"]:
                        if item_id in pool and item_id not in selected:
                            slide.exam_anchor_ids = [item_id]
                            break
                    if slide.exam_anchor_ids:
                        break
        selected.extend(slide.exam_anchor_ids)
        if not slide.script.analogy:
            slide.script = agents.fallback_script(
                slide.title, slide.kp, pool.get(slide.exam_anchor_ids[0]) if slide.exam_anchor_ids else None
            )
    # 总锚点不足 6 道时从精选题库补
    if len(set(selected)) < exam_count:
        extras = [i for i in pool if i not in selected and pool[i].get("source_type") == "reference_paper"]
        extras += [i for i in pool if i not in selected and i not in extras]
        for item_id in extras:
            if len(set(selected)) >= exam_count:
                break
            for slide in valid:
                if item_id in next(
                    (c["candidates"] for c in CURATED_SLIDES if c["kp"] == slide.kp), []
                ):
                    slide.exam_anchor_ids.append(item_id)
                    selected.append(item_id)
                    break
    # 难度兜底：模型可能只挑简单题，代码层强制执行易/中/难配比
    selected = _balance_difficulties(valid, pool, selected, exam_count)
    if len(set(selected)) < 6:
        return None
    draft.slides = valid
    draft.objectives = draft.objectives or _lesson_objectives(params.get("chapter", "有理数的加减运算"))
    return draft


class CoursewareService:
    async def generate(self, params: dict, teacher_id: str) -> dict:
        chapter = params.get("chapter", "有理数的加减运算")
        subject = params.get("subject", "数学")
        grade = params.get("grade", "七年级")
        exam_count = int(params.get("exam_count", 10))

        contexts = rag_service.search(
            f"{chapter} 加法 减法 混合运算 符号 绝对值",
            kind="textbook",
            top_k=6,
        )
        pool = {
            item["id"]: item
            for item in question_bank.list_items(subject=subject, grade=grade, limit=200)
        }
        # 若题库为空，至少给出明确错误
        if not pool:
            raise ValueError("题库为空，请先导入参考试卷或示例题")

        draft = None
        used_llm = False
        if params.get("use_llm", True) and llm.available:
            draft = await agents.agents.courseware(params, contexts, list(pool.values()))
            if draft:
                draft = _normalize_llm_draft(draft, params, pool, exam_count)
            used_llm = draft is not None
        if draft is None:
            draft = _fallback_draft(params, pool, exam_count)

        lesson_id = f"lesson_{uuid.uuid4().hex[:10]}"
        all_anchor_ids = [i for slide in draft.slides for i in slide.exam_anchor_ids]
        coverage = question_bank.coverage_stats(all_anchor_ids)
        now = db.now_ms()
        db.execute(
            "INSERT INTO lessons(id, teacher_id, title, subject, grade, textbook_version, chapter, objectives, "
            "exam_coverage, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                lesson_id,
                teacher_id,
                draft.title,
                subject,
                grade,
                params.get("textbook_version", "北师大版（2026）"),
                chapter,
                dumps(draft.objectives),
                dumps(coverage),
                now,
                now,
            ),
        )
        for idx, slide in enumerate(draft.slides):
            slide_id = f"slide_{lesson_id}_{idx:02d}"
            db.execute(
                "INSERT INTO slides(id, lesson_id, ord, title, bullets, kp, script, exam_anchor_ids) VALUES(?,?,?,?,?,?,?,?)",
                (
                    slide_id,
                    lesson_id,
                    idx,
                    slide.title,
                    dumps(slide.bullets),
                    slide.kp,
                    dumps(slide.script.model_dump()),
                    dumps(slide.exam_anchor_ids),
                ),
            )
        lesson = self.get_lesson(lesson_id)
        lesson["rag_contexts"] = [
            {"chunk_id": c["chunk_id"], "source": c.get("source", ""), "score": c.get("score", 0), "content": c["content"]}
            for c in contexts
        ]
        lesson["llm_used"] = used_llm
        return lesson

    def list_lessons(self, teacher_id: str | None = None) -> list[dict]:
        if teacher_id:
            rows = db.query("SELECT * FROM lessons WHERE teacher_id=? ORDER BY created_at DESC", (teacher_id,))
        else:
            rows = db.query("SELECT * FROM lessons ORDER BY created_at DESC")
        return [self._decorate(row, with_slides=False) for row in rows]

    def get_lesson(self, lesson_id: str) -> dict:
        row = db.query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
        if not row:
            raise ValueError("课件不存在")
        return self._decorate(row, with_slides=True)

    def _decorate(self, row: dict, with_slides: bool) -> dict:
        lesson = dict(row)
        lesson["objectives"] = loads(lesson.get("objectives"), [])
        lesson["exam_coverage"] = loads(lesson.get("exam_coverage"), {})
        if not with_slides:
            return lesson
        slides = db.query("SELECT * FROM slides WHERE lesson_id=? ORDER BY ord", (row["id"],))
        decorated = []
        for slide in slides:
            item = dict(slide)
            item["bullets"] = loads(item.get("bullets"), [])
            item["script"] = loads(item.get("script"), {})
            anchor_ids = loads(item.get("exam_anchor_ids"), [])
            item["exam_anchor_ids"] = anchor_ids
            item["exam_anchors"] = question_bank.get_items(anchor_ids)
            decorated.append(item)
        lesson["slides"] = decorated
        all_ids = [i for slide in decorated for i in slide["exam_anchor_ids"]]
        lesson["exam_coverage"] = question_bank.coverage_stats(all_ids)
        return lesson

    def update_slide(self, lesson_id: str, slide_id: str, patch: SlidePatch) -> dict:
        slide = db.query_one("SELECT * FROM slides WHERE id=? AND lesson_id=?", (slide_id, lesson_id))
        if not slide:
            raise ValueError("幻灯片不存在")
        updates = []
        params: list[Any] = []
        if patch.title is not None:
            updates.append("title=?")
            params.append(patch.title)
        if patch.bullets is not None:
            updates.append("bullets=?")
            params.append(dumps(patch.bullets))
        if patch.script is not None:
            updates.append("script=?")
            params.append(dumps(patch.script.model_dump()))
        if patch.exam_anchor_ids is not None:
            valid = [i for i in patch.exam_anchor_ids if question_bank.get_item(i)]
            updates.append("exam_anchor_ids=?")
            params.append(dumps(valid))
        if not updates:
            return slide
        params.extend([slide_id, lesson_id])
        db.execute(f"UPDATE slides SET {', '.join(updates)} WHERE id=? AND lesson_id=?", params)
        db.execute("UPDATE lessons SET updated_at=? WHERE id=?", (db.now_ms(), lesson_id))
        lesson = self.get_lesson(lesson_id)
        return next((s for s in lesson["slides"] if s["id"] == slide_id), {})

    def delete_lesson(self, lesson_id: str) -> dict:
        """删除课件及其幻灯片；已被课堂使用时拒绝删除。"""
        lesson = db.query_one("SELECT * FROM lessons WHERE id=?", (lesson_id,))
        if not lesson:
            raise ValueError("课件不存在")
        used = db.query_one("SELECT COUNT(*) AS n FROM classroom_sessions WHERE lesson_id=?", (lesson_id,))["n"]
        if used:
            raise ValueError(f"该课件已被 {used} 堂课堂使用，不能删除")
        db.execute("DELETE FROM slides WHERE lesson_id=?", (lesson_id,))
        db.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
        return {"id": lesson_id, "title": lesson.get("title") or ""}

    def export(self, lesson_id: str, fmt: str) -> Path:
        lesson = self.get_lesson(lesson_id)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = "".join(ch for ch in lesson["title"] if ch.isalnum() or ch in "·_-")[:30] or "lesson"
        if fmt == "json":
            path = EXPORT_DIR / f"{safe_title}_{lesson_id}.json"
            path.write_text(json.dumps(lesson, ensure_ascii=False, indent=2), encoding="utf-8")
            return path
        path = EXPORT_DIR / f"{safe_title}_{lesson_id}.pptx"
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        # 封面
        cover = prs.slides.add_slide(prs.slide_layouts[0])
        cover.shapes.title.text = lesson["title"]
        cover.placeholders[1].text = f"{lesson.get('grade', '')} · {lesson.get('subject', '')} · {lesson.get('chapter', '')}"
        for slide in lesson["slides"]:
            page = prs.slides.add_slide(prs.slide_layouts[1])
            page.shapes.title.text = slide["title"]
            body = page.placeholders[1].text_frame
            body.clear()
            for idx, bullet in enumerate(slide["bullets"]):
                paragraph = body.paragraphs[0] if idx == 0 else body.add_paragraph()
                paragraph.text = f"• {bullet}"
                paragraph.font.size = Pt(22)
                paragraph.font.name = "Microsoft YaHei"
            script = slide.get("script", {})
            notes = page.notes_slide.notes_text_frame
            notes.text = (
                f"【生活类比】{script.get('analogy', '')}\n"
                f"【分步推导】{'；'.join(script.get('derivation_steps', []))}\n"
                f"【易错点】{'；'.join(script.get('pitfalls', []))}\n"
                f"【真题应用】{script.get('exam_application', '')}\n"
                f"【引用题目】{', '.join(i['id'] for i in slide.get('exam_anchors', []))}"
            )
            anchors = slide.get("exam_anchors", [])
            if anchors:
                box = page.shapes.add_textbox(Inches(0.6), Inches(6.2), Inches(12.2), Inches(0.8))
                box.text_frame.text = "真题锚点：" + "；".join(
                    f"{a['id']}（{a['difficulty']}·{a.get('source_type', '')}）" for a in anchors
                )
                for paragraph in box.text_frame.paragraphs:
                    paragraph.font.size = Pt(12)
                    paragraph.font.name = "Microsoft YaHei"
        prs.save(str(path))
        return path


courseware_service = CoursewareService()
