"""多智能体角色：教师、学生、助教、批改、诊断、备课。

设计原则：后端状态机决定“谁在什么时候说什么”，模型只负责在固定 JSON 契约内生成内容；
模型不可用时全部走确定性教学脚本，保证离线可演示。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .json_utils import answers_equal, compact, guess_error_type
from .llm import llm
from .schemas import (
    AssistantReply,
    CoursewareDraft,
    CoursewareSlide,
    DiagnosisResult,
    GradeResult,
    SlideScript,
    StudentQuestion,
    StudentQuestionList,
)


SCRIPT_LIBRARY: dict[str, dict[str, Any]] = {
    "情境导入": {
        "analogy": "把今天的零花钱记成一本账：妈妈给你 10 元记 +10，买文具花掉 6 元记 -6。要算还剩多少，就是把 +10 和 -6 合起来。",
        "steps": [
            "先规定正方向：收入、向东、上升记为正；支出、向西、下降记为负。",
            "把每一笔收支写成一个带符号的数。",
            "把几笔收支合并，就是有理数的加法。",
            "结果为正表示结余/向东，结果为负表示透支/向西。",
        ],
        "pitfalls": ["把支出记成正数，方向反了。", "忽略 0 既不是正数也不是负数。"],
        "exam": "参考试卷第 2 题用足球质量偏差考查“绝对值越小越接近标准”，本质是把正负号看成一个方向。",
    },
    "同号": {
        "analogy": "两次都向东走：先走 3 米，再走 5 米，一共向东 8 米；两次都向西走，就是一共向西 8 米。同向就叠加。",
        "steps": ["看两个数的符号是否相同。", "符号不变，取相同的符号。", "把两个数的绝对值相加。", "写出结果并检验方向。"],
        "pitfalls": ["(-3)+(-5) 错算成 -2：把同号相加当成异号相减。", "忘记写负号，得到 +8。"],
        "exam": "先看符号，再算绝对值。例：(-7)+(-5)=-(7+5)=-12。",
    },
    "异号": {
        "analogy": "收入 8 元、支出 5 元，净收入 3 元；支出 8 元、收入 5 元，净支出 3 元。方向相反，先抵消，再看谁多。",
        "steps": ["比较两个数的绝对值，找出较大者。", "结果的符号取绝对值较大的数的符号。", "用较大的绝对值减去较小的绝对值。", "绝对值相等时，结果是 0。"],
        "pitfalls": ["把绝对值相加，如 (-8)+3 算成 -11。", "符号取错：支出更多时应为负。"],
        "exam": "参考第 4 题：数轴上 b<0<a，ab<0；a+b 的符号要看 |a| 与 |b| 谁大，题目没给就不能确定。",
    },
    "相反数": {
        "analogy": "向东走 6 米，再向西走 6 米，回到原点；收入 6 元又支出 6 元，结余为 0。",
        "steps": ["识别两个数是否只有符号不同。", "互为相反数的两个数相加得 0。", "任何数与 0 相加仍得这个数。", "用 a+(-a)=0 化简。"],
        "pitfalls": ["把相反数与倒数混淆：相反数和为 0，倒数积为 1。", "认为 0 的相反数是 0 以外的数。"],
        "exam": "参考第 21 题：m 与 n 互为相反数，直接得到 m+n=0，再用 p、q 求值。",
    },
    "减法": {
        "analogy": "欠了 3 元，相当于 -3；现在还掉这笔欠款，相当于加上 3。减去一个数，就是加上它的相反数。",
        "steps": ["把减号改写成加号。", "把减数改成它的相反数。", "按有理数加法法则计算。", "用“差+减数=被减数”检验。"],
        "pitfalls": ["只改减号，忘记把减数变相反数，如 5-(-7) 算成 5-7。", "把 -3-4 算成 -1。"],
        "exam": "参考第 18(1) 题：12-(-18)+(-7)-20=12+18-7-20=3。",
    },
    "混合": {
        "analogy": "记账时先把所有收入和支出都写成加法，再把能凑整的放在一起，算起来更快。",
        "steps": ["把所有减法统一成加法。", "省略加号和括号，写成代数和。", "利用交换律、结合律把相反数或凑整的数分组。", "按顺序计算并检验。"],
        "pitfalls": ["去括号时符号出错，尤其是括号前是减号。", "不统一成加法就随意交换，导致符号混乱。"],
        "exam": "参考第 20 题：把八次位移相加得 -3，说明收工时在 A 地西边 3km；总路程要把绝对值相加。",
    },
    "真题": {
        "analogy": "把今天的规则放进真实题目里：先判断方向，再选加法或减法，最后按步骤算。",
        "steps": ["读题，圈出正方向和各数据。", "把文字转成带符号的算式。", "按同号/异号规则计算。", "回到题目情境检验答案是否合理。"],
        "pitfalls": ["只算数值，不回答“方向/结余/温度”等实际含义。", "多问综合题漏答某一问。"],
        "exam": "用第 20、22、23 题做分层练习：先做直接计算，再做数轴距离，最后做裂项相消。",
    },
}

DEFAULT_SCRIPT = {
    "analogy": "把正负数看成收入和支出：同向就叠加，反向先抵消。",
    "steps": ["先看符号。", "再算绝对值。", "按规则定符号。", "回到情境检验。"],
    "pitfalls": ["忽略符号。", "把同号和异号规则混用。"],
    "exam": "用一道同类题立即检验规则是否会用。",
}


def _script_key(title: str, kp: str) -> str:
    haystack = f"{title}{kp}"
    if "真题" in haystack or "演练" in haystack:
        return "真题"
    if "情境" in haystack or "导入" in haystack or "账本" in haystack or "走进" in haystack:
        return "情境导入"
    if "混合" in haystack:
        return "混合"
    # 先判断“减法”：减法标题里常出现“相反数”，不能先命中相反数分支
    if "减法" in haystack:
        return "减法"
    if "同号" in haystack:
        return "同号"
    if "相反" in haystack or "倒数" in haystack:
        return "相反数"
    if "异号" in haystack or "加法" in haystack:
        return "异号"
    return "情境导入"


def fallback_script(title: str, kp: str, exam_item: Optional[dict] = None) -> SlideScript:
    entry = SCRIPT_LIBRARY.get(_script_key(title, kp), DEFAULT_SCRIPT)
    exam = entry["exam"]
    if exam_item:
        exam = f"{exam_item['stem']}\n解题提示：先判断符号，再按规则计算；参考解析：{compact(exam_item.get('analysis', ''), 90)}"
    return SlideScript(
        analogy=entry["analogy"],
        derivation_steps=list(entry["steps"]),
        pitfalls=list(entry["pitfalls"]),
        exam_application=exam,
    )


DEF_QUESTIONS = {
    "有理数的加法": [
        ("为什么 (-3)+(-5) 不是 -2，而是 -8？我总想把 3 和 5 相减。", "同号相加误用异号法则", "medium"),
        ("(-8)+3 为什么等于 -5，而不是 -11？", "异号相加把绝对值相加", "easy"),
    ],
    "有理数的减法": [
        ("5-(-7) 为什么等于 12？减号后面是负数，不是应该更小吗？", "没有把减法转成加法", "medium"),
        ("-3-4 为什么是 -7？", "忽略第二个数的负号", "easy"),
    ],
    "相反数与倒数": [
        ("相反数和倒数有什么区别？", "混淆和为 0 与积为 1", "easy"),
        ("0 有相反数吗？有倒数吗？", "认为 0 的倒数也是 0", "medium"),
    ],
    "有理数加减混合运算": [
        ("加减混合运算可以先算后面的吗？", "不统一成加法就随意交换", "medium"),
        ("去括号时什么时候变号？", "括号前是减号时忘记变号", "medium"),
    ],
    "有理数加减应用": [
        ("题目里的“向西为负”怎么用？", "正方向没有先规定", "easy"),
        ("为什么路程要把绝对值相加，而位移直接相加？", "混淆位移与路程", "hard"),
    ],
    "数轴与绝对值": [
        ("数轴上两点的距离为什么用绝对值？", "距离不能为负", "easy"),
        ("|x+1|=5 为什么有两个答案？", "只考虑一个方向", "medium"),
    ],
}


def fallback_questions(slide: dict) -> list[StudentQuestion]:
    kp = slide.get("kp", "")
    pairs = DEF_QUESTIONS.get(kp) or DEF_QUESTIONS.get("有理数加减混合运算", [])
    if "相反" in slide.get("title", ""):
        pairs = DEF_QUESTIONS["相反数与倒数"]
    return [StudentQuestion(question=q, misconception=m, difficulty=d) for q, m, d in pairs]


def fallback_reply(slide: dict, question: str, hint_level: int) -> AssistantReply:
    entry = SCRIPT_LIBRARY.get(_script_key(slide.get("title", ""), slide.get("kp", "")), DEFAULT_SCRIPT)
    steps = entry["steps"]
    level = max(0, min(3, hint_level))
    if level == 0:
        return AssistantReply(
            hint_level=0,
            probing_question="先别急着算：你觉得这两个数是同向还是反向？结果应该比原来的数更大还是更小？",
            steps=[],
            analogy=entry["analogy"],
        )
    if level == 1:
        return AssistantReply(
            hint_level=1,
            probing_question="先判断符号：两个数是同号还是异号？",
            steps=steps[:2],
            analogy=entry["analogy"],
        )
    if level == 2:
        return AssistantReply(
            hint_level=2,
            probing_question="你已经有思路了，试着把最后一步自己写出来。",
            steps=steps[:3],
            analogy=entry["analogy"],
        )
    return AssistantReply(
        hint_level=3,
        probing_question="回头看看：你刚才卡住的是符号，还是绝对值运算？",
        steps=steps,
        analogy=entry["analogy"],
        final_answer="规则：先定符号，再算绝对值，最后回到情境检验。以 (-8)+3 为例：异号，|-8|>|3|，取负号，8-3=5，所以结果是 -5。",
    )


class Agents:
    async def courseware(
        self,
        params: dict,
        contexts: list[dict],
        exam_items: list[dict],
    ) -> Optional[CoursewareDraft]:
        if not llm.available:
            return None
        context_text = "\n\n".join(
            f"[{c.get('chunk_id', '')}] {compact(c.get('content', ''), 700)}" for c in contexts[:6]
        )
        exam_text = "\n".join(
            f"- id={item['id']} | {item['difficulty']} | {item['kp']} | {compact(item['stem'], 80)} | 来源={item.get('source', '')}"
            for item in exam_items[:14]
        )
        system = (
            "你是中小学数学教研员，擅长把教材、课标与参考试卷组合成一节可互动讲授的课。"
            "硬性要求：1) 只能引用给定的教材片段和题目 id，不得编造题目或出处；"
            "2) 每张幻灯片的讲解必须包含生活类比、分步推导、易错点、真题应用；"
            "3) 题目要覆盖容易/中等/较难，优先使用参考试卷题；"
            "4) 只输出 JSON。"
        )
        user = (
            f"备课参数：{json.dumps(params, ensure_ascii=False)}\n\n"
            f"教材片段：\n{context_text}\n\n"
            f"可用题目：\n{exam_text}\n\n"
            "请生成 6~8 张幻灯片。exam_anchor_ids 只能填上面列出的题目 id；"
            "citations 只能填教材片段的 chunk_id。"
        )
        result = await llm.chat_json(system, user, CoursewareDraft, temperature=0.4)
        if result is None:
            return None
        if len(result.slides) < 5:
            return None
        valid_ids = {item["id"] for item in exam_items}
        cleaned = []
        for slide in result.slides:
            slide.exam_anchor_ids = [i for i in slide.exam_anchor_ids if i in valid_ids]
            if not all([slide.script.analogy, slide.script.derivation_steps, slide.script.pitfalls, slide.script.exam_application]):
                fallback = fallback_script(slide.title, slide.kp)
                slide.script = fallback
            cleaned.append(slide)
        result.slides = cleaned
        return result

    async def teacher_script(self, slide: dict, contexts: list[dict], exam_item: Optional[dict] = None) -> SlideScript:
        base = fallback_script(slide.get("title", ""), slide.get("kp", ""), exam_item)
        if not llm.available:
            return base
        system = (
            "你是初中数学老师。请把知识点讲得让基础一般的学生也能听懂："
            "先给生活类比，再给分步推导，再点出易错点，最后落到一道真题/参考题。"
            "只能引用给定材料，不得编造题目出处。只输出 JSON。"
        )
        user = (
            f"幻灯片：{slide.get('title')}\n知识点：{slide.get('kp')}\n要点：{slide.get('bullets')}\n\n"
            f"教材片段：\n" + "\n".join(compact(c.get('content', ''), 500) for c in contexts[:4]) +
            f"\n\n参考题：{json.dumps(exam_item, ensure_ascii=False) if exam_item else '无'}"
        )
        result = await llm.chat_json(system, user, SlideScript, temperature=0.4)
        if result is None:
            return base
        if not result.analogy:
            result.analogy = base.analogy
        if not result.derivation_steps:
            result.derivation_steps = base.derivation_steps
        if not result.pitfalls:
            result.pitfalls = base.pitfalls
        if not result.exam_application:
            result.exam_application = base.exam_application
        return result

    async def student_questions(self, slide: dict, exam_items: list[dict]) -> list[StudentQuestion]:
        base = fallback_questions(slide)
        if not llm.available:
            return base
        system = (
            "你在扮演一名七年级学生，数学基础中等。请根据当前幻灯片，提出 2 个真实学生会问的问题，"
            "并写出对应的典型误解。问题要具体、口语化，不要像老师总结。只输出 JSON。"
        )
        user = (
            f"幻灯片：{slide.get('title')}\n知识点：{slide.get('kp')}\n要点：{slide.get('bullets')}\n"
            f"相关题目：{json.dumps([{'stem': i['stem'], 'difficulty': i['difficulty']} for i in exam_items[:3]], ensure_ascii=False)}"
        )
        result = await llm.chat_json(system, user, StudentQuestionList, temperature=0.7)
        if result is None or not result.questions:
            return base
        return result.questions[:2]

    async def assistant_reply(self, slide: dict, question: str, hint_level: int) -> AssistantReply:
        base = fallback_reply(slide, question, hint_level)
        if not llm.available:
            return base
        system = (
            "你是课堂 AI 助教，采用苏格拉底式引导："
            "0 级只追问，不给步骤和答案；1 级给生活类比和第一步；2 级给完整思路但不直接给最终数值答案；"
            "3 级才给答案并复盘。绝不能在 0~2 级泄露最终答案。只输出 JSON。"
        )
        user = (
            f"当前幻灯片：{slide.get('title')}\n知识点：{slide.get('kp')}\n"
            f"学生问题：{question}\n当前提示级别：{hint_level}\n"
            "请给出 probing_question、steps、analogy，必要时给 final_answer。"
        )
        result = await llm.chat_json(system, user, AssistantReply, temperature=0.5)
        if result is None:
            return base
        result.hint_level = hint_level
        if hint_level < 3:
            result.final_answer = ""
        if not result.probing_question:
            result.probing_question = base.probing_question
        if not result.steps:
            result.steps = base.steps
        if not result.analogy:
            result.analogy = base.analogy
        return result

    async def grade(self, item: dict, answer: str) -> GradeResult:
        expected = item.get("answer", "")
        correct = answers_equal(expected, answer)
        if correct:
            return GradeResult(
                correct=True,
                score=1,
                error_type="",
                step_feedback=["符号判断正确。", "绝对值运算正确。", "结果与答案一致。"],
                explanation=item.get("analysis", ""),
            )
        if not answer.strip():
            return GradeResult(
                correct=False,
                score=0,
                error_type="未作答",
                step_feedback=["先写出已知条件和要求的量。", "再按同号/异号规则列式。"],
                explanation=item.get("analysis", ""),
            )
        if llm.available and item.get("qtype") in {"word", "fill"}:
            system = (
                "你是严谨但鼓励学生的数学批改老师。请依据题目、参考答案与解析判断学生答案是否正确；"
                "如果学生只答对部分小问，判为不正确，但在反馈中指出已答对的部分。只输出 JSON。"
            )
            user = (
                f"题目：{item.get('stem')}\n参考答案：{expected}\n解析：{item.get('analysis', '')}\n"
                f"学生答案：{answer}\n请给出 correct、score(0或1)、error_type、step_feedback、explanation。"
            )
            result = await llm.chat_json(system, user, GradeResult, temperature=0.2)
            if result is not None:
                result.score = 1 if result.correct else 0
                if result.correct:
                    result.error_type = ""
                elif not result.error_type:
                    result.error_type = guess_error_type(expected, answer)
                if not result.explanation:
                    result.explanation = item.get("analysis", "")
                return result
        error_type = guess_error_type(expected, answer)
        feedback = [
            "先检查符号：结果应该取哪个符号？",
            "再检查绝对值：应该相加还是相减？",
            f"你的答案“{compact(answer, 40)}”与参考答案不一致，请对照解析逐步复盘。",
        ]
        return GradeResult(
            correct=False,
            score=0,
            error_type=error_type,
            step_feedback=feedback,
            explanation=item.get("analysis", ""),
        )

    async def diagnosis(self, student_name: str, mastery: list[dict], weak: list[str], error_counts: dict[str, int]) -> DiagnosisResult:
        if not llm.available:
            if weak:
                summary = f"{student_name} 当前薄弱知识点是：{'、'.join(weak)}。建议先回看生活类比和分步推导，再做 3 道同知识点基础题。"
            else:
                summary = f"{student_name} 当前各知识点掌握较稳，建议继续做中等难度综合题，保持每天 10 分钟的计算练习。"
            return DiagnosisResult(summary=summary, weak_points=weak, recommended_question_ids=[])
        system = (
            "你是学情诊断老师。请用 60 字左右给出一段具体、可执行的建议，"
            "指出薄弱知识点和一个练习动作。不要空泛表扬。只输出 JSON。"
        )
        user = (
            f"学生：{student_name}\n掌握度：{json.dumps(mastery, ensure_ascii=False)}\n"
            f"薄弱点：{weak}\n错因统计：{json.dumps(error_counts, ensure_ascii=False)}"
        )
        result = await llm.chat_json(system, user, DiagnosisResult, temperature=0.4)
        if result is None:
            return DiagnosisResult(summary="先回看错题解析，再做同知识点基础题巩固。", weak_points=weak)
        result.weak_points = result.weak_points or weak
        return result

    async def summary(self, lesson: dict, slide_count: int, questions: list[str], weak: list[str]) -> str:
        if llm.available:
            system = "你是课堂总结老师，请用 3~5 句话总结本节核心规则、易错点和下一步练习。不要编造题目。"
            user = (
                f"课题：{lesson.get('title')}\n目标：{lesson.get('objectives')}\n"
                f"幻灯片数：{slide_count}\n学生问题：{questions[:4]}\n薄弱点：{weak}"
            )
            text = await llm.chat(system, user, temperature=0.3, max_tokens=400)
            if text:
                return text
        return (
            f"本节《{lesson.get('title', '有理数的加减运算')}》我们抓住了一条主线：先定方向，再定符号，最后算绝对值。"
            "同号相加就叠加；异号相加先抵消，取绝对值较大者的符号；减法先转成加法，减数变相反数；混合运算先统一成加法，再凑整。"
            f"大家问到最多的是：{('、'.join(questions[:2]) if questions else '符号判断和减法转化')}。"
            f"课后先练 3 道基础计算，再做 1 道数轴/实际应用题，重点检查符号和去括号。"
        )


agents = Agents()
