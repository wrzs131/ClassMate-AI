"""题库查询、组卷与覆盖度统计。"""
from __future__ import annotations

from typing import Any, Iterable

from .. import db
from ..db import loads


def _row_to_item(row: dict, include_answer: bool = True) -> dict:
    item = dict(row)
    item["options"] = loads(item.get("options"), [])
    if not include_answer:
        for key in ("answer", "analysis", "derived_from"):
            item.pop(key, None)
    return item


def list_items(
    kp: str | None = None,
    difficulty: str | None = None,
    subject: str | None = None,
    grade: str | None = None,
    qtype: str | None = None,
    limit: int | None = None,
    include_answer: bool = True,
) -> list[dict]:
    sql = "SELECT * FROM exam_items WHERE 1=1"
    params: list[Any] = []
    if kp:
        sql += " AND kp LIKE ?"
        params.append(f"%{kp}%")
    if difficulty:
        sql += " AND difficulty=?"
        params.append(difficulty)
    if subject:
        sql += " AND subject=?"
        params.append(subject)
    if grade:
        sql += " AND grade=?"
        params.append(grade)
    if qtype:
        sql += " AND qtype=?"
        params.append(qtype)
    sql += " ORDER BY CASE difficulty WHEN 'easy' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_item(row, include_answer) for row in db.query(sql, params)]


def get_item(item_id: str, include_answer: bool = True) -> dict | None:
    row = db.query_one("SELECT * FROM exam_items WHERE id=?", (item_id,))
    return _row_to_item(row, include_answer) if row else None


def get_items(item_ids: Iterable[str], include_answer: bool = True) -> list[dict]:
    ids = list(dict.fromkeys(item_ids))
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = db.query(f"SELECT * FROM exam_items WHERE id IN ({placeholders})", ids)
    by_id = {row["id"]: _row_to_item(row, include_answer) for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def select_for_quiz(kps: list[str], mix: dict[str, int] | None = None, total: int = 5) -> list[dict]:
    mix = mix or {"easy": 2, "medium": 2, "hard": 1}
    pool = []
    for kp in kps:
        pool.extend(list_items(kp=kp))
    if not pool:
        pool = list_items()
    seen = set()
    unique = []
    for item in pool:
        if item["id"] not in seen:
            unique.append(item)
            seen.add(item["id"])

    selected: list[dict] = []
    # 1) 先保证至少 2 道参考试卷题（能溯源）
    for item in unique:
        if item.get("source_type") == "reference_paper" and len(selected) < 2:
            selected.append(item)
    # 2) 按难度配比补足
    for difficulty, count in mix.items():
        current = sum(1 for item in selected if item["difficulty"] == difficulty)
        need = max(0, int(count) - current)
        for item in unique:
            if need <= 0:
                break
            if item["difficulty"] == difficulty and item not in selected:
                selected.append(item)
                need -= 1
    # 3) 不足 total 时从剩余题补
    for item in unique:
        if len(selected) >= total:
            break
        if item not in selected:
            selected.append(item)
    return selected[:total]


def coverage_stats(item_ids: Iterable[str]) -> dict:
    items = get_items(item_ids)
    diff = {"easy": 0, "medium": 0, "hard": 0}
    sources = {"reference_paper": 0, "sample_adapted": 0, "other": 0}
    for item in items:
        diff[item["difficulty"]] = diff.get(item["difficulty"], 0) + 1
        if item.get("source_type") == "reference_paper":
            sources["reference_paper"] += 1
        elif item.get("source_type") == "sample_adapted":
            sources["sample_adapted"] += 1
        else:
            sources["other"] += 1
    return {
        "total": len(items),
        "difficulty": diff,
        "sources": sources,
        "reference_ratio": round(sources["reference_paper"] / max(1, len(items)), 3),
    }


def recommend_similar(kps: list[str], exclude_ids: Iterable[str], limit: int = 3) -> list[dict]:
    excluded = set(exclude_ids)
    pool = []
    for kp in kps:
        pool.extend(list_items(kp=kp))
    pool = [item for item in pool if item["id"] not in excluded]
    pool.sort(key=lambda item: (item["source_type"] != "reference_paper", item["difficulty"] != "medium"))
    return pool[:limit]
