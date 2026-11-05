"""模型输出解析与答案判定工具。"""
from __future__ import annotations

import json
import re
from fractions import Fraction
from typing import Any


def extract_json(text: str) -> Any:
    """从模型输出中提取第一个合法 JSON（兼容代码块、前后说明文字）。"""
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(cleaned):
        if ch not in "{[":
            continue
        try:
            obj, _ = decoder.raw_decode(cleaned, idx)
            return obj
        except Exception:
            continue
    return None


def normalize_answer(value: Any) -> str:
    text = str(value or "").strip()
    text = text.replace("＝", "=").replace("（", "(").replace("）", ")")
    text = text.replace("，", ",").replace("。", "")
    text = text.replace(" ", "").replace("\n", "")
    text = text.replace("$", "").replace("\\", "")
    text = re.sub(r"^(答|答案|正确答案)[:：]", "", text)
    return text.strip().lower()


def parse_number(value: Any) -> float | None:
    """解析整数、小数、分数、带分数与简单百分数。"""
    text = normalize_answer(value)
    if not text:
        return None
    text = text.replace("%", "") if text.endswith("%") else text
    try:
        if "/" in text and len(text) <= 20:
            return float(Fraction(text))
        return float(text)
    except Exception:
        pass

    mixed = re.fullmatch(r"(-?\d+)\s*又\s*(\d+)/(\d+)", text)
    if mixed:
        whole, num, den = mixed.groups()
        base = abs(int(whole))
        val = base + int(num) / int(den)
        return -val if int(whole) < 0 else val

    frac = re.search(r"(-?\d+)/(\d+)", text)
    if frac:
        try:
            return float(Fraction(int(frac.group(1)), int(frac.group(2))))
        except Exception:
            return None
    return None


def _single_equal(expected: Any, actual: Any) -> bool:
    """单值比较：选择题字母、数值等价、多空同序。"""
    exp = normalize_answer(expected)
    act = normalize_answer(actual)
    if not act:
        return False
    if exp == act:
        return True

    # 选择题：允许 "B" / "B." / "B、xxx"
    if len(exp) == 1 and exp in "abcd" and act[:1] in "abcd":
        return True

    exp_num = parse_number(exp)
    act_num = parse_number(act)
    if exp_num is not None and act_num is not None:
        return abs(exp_num - act_num) <= 1e-6

    # 多空题：比较每个非空片段
    if any(sep in exp for sep in [";", "；", ","]):
        parts_exp = [p for p in re.split(r"[;；,，]", exp) if p]
        parts_act = [p for p in re.split(r"[;；,，]", act) if p]
        if len(parts_exp) == len(parts_act):
            return all(
                normalize_answer(a) == normalize_answer(b)
                or (parse_number(a) is not None and parse_number(b) is not None and abs(parse_number(a) - parse_number(b)) <= 1e-6)
                for a, b in zip(parts_exp, parts_act)
            )
    return False


def answers_equal(expected: Any, actual: Any) -> bool:
    """答案判定：支持多解题（用“或”连接，顺序不限）。"""
    exp = normalize_answer(expected)
    act = normalize_answer(actual)
    if not act:
        return False
    if "或" in exp or "或" in act:
        parts_exp = [p for p in re.split(r"或者|或", exp) if p]
        parts_act = [p for p in re.split(r"或者|或", act) if p]
        if len(parts_exp) != len(parts_act):
            return False
        remaining = list(parts_act)
        for part in parts_exp:
            hit = next((cand for cand in remaining if _single_equal(part, cand)), None)
            if hit is None:
                return False
            remaining.remove(hit)
        return True
    return _single_equal(exp, act)


def guess_error_type(expected: Any, actual: Any) -> str:
    if not normalize_answer(actual):
        return "未作答"
    exp_num = parse_number(expected)
    act_num = parse_number(actual)
    if exp_num is not None and act_num is not None:
        if abs(exp_num + act_num) <= 1e-6:
            return "符号错误"
        if abs(abs(exp_num) - abs(act_num)) <= 1e-6:
            return "符号错误"
        return "计算失误"
    exp = normalize_answer(expected)
    act = normalize_answer(actual)
    if exp and act and exp[0] != act[0] and exp[1:] == act[1:]:
        return "符号错误"
    return "答案不一致"


def compact(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text[:limit]
