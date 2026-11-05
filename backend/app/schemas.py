"""Pydantic 契约：模型输出与 API 入参。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SlideScript(BaseModel):
    analogy: str = ""
    derivation_steps: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    exam_application: str = ""
    citations: list[str] = Field(default_factory=list)


class CoursewareSlide(BaseModel):
    title: str
    bullets: list[str] = Field(default_factory=list)
    kp: str = ""
    script: SlideScript = Field(default_factory=SlideScript)
    exam_anchor_ids: list[str] = Field(default_factory=list)


class CoursewareDraft(BaseModel):
    title: str
    objectives: list[str] = Field(default_factory=list)
    slides: list[CoursewareSlide] = Field(default_factory=list)


class StudentQuestion(BaseModel):
    question: str
    misconception: str = ""
    difficulty: Literal["easy", "medium", "hard"] = "easy"


class StudentQuestionList(BaseModel):
    questions: list[StudentQuestion] = Field(default_factory=list)


class AssistantReply(BaseModel):
    hint_level: int = 0
    probing_question: str = ""
    steps: list[str] = Field(default_factory=list)
    analogy: str = ""
    final_answer: str = ""


class GradeResult(BaseModel):
    correct: bool = False
    score: int = 0
    error_type: str = ""
    step_feedback: list[str] = Field(default_factory=list)
    explanation: str = ""


class DiagnosisResult(BaseModel):
    summary: str = ""
    weak_points: list[str] = Field(default_factory=list)
    recommended_question_ids: list[str] = Field(default_factory=list)


# ---------- API 入参 ----------

class RegisterRequest(BaseModel):
    role: Literal["teacher", "student"]
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=6, max_length=64)
    nickname: str = Field(min_length=1, max_length=24)


class LoginRequest(BaseModel):
    username: str
    password: str


class SpaceCreateRequest(BaseModel):
    kind: Literal["textbook", "exam", "standard", "mistake"]
    name: str
    subject: str = ""
    grade: str = ""
    textbook_version: str = ""
    description: str = ""


class ExamItemInput(BaseModel):
    kp: str
    qtype: str = "choice"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    stem: str
    options: list[str] = Field(default_factory=list)
    answer: str
    analysis: str = ""
    source: str = ""
    source_type: str = "sample_adapted"
    year: str = ""
    region: str = ""
    derived_from: str = ""
    subject: str = "数学"
    grade: str = "七年级"


class ExamImportRequest(BaseModel):
    items: list[ExamItemInput]


class RagSearchRequest(BaseModel):
    query: str
    space_ids: list[str] = Field(default_factory=list)
    kind: str | None = None
    kp: str | None = None
    top_k: int = 5


class CoursewareRequest(BaseModel):
    subject: str = "数学"
    grade: str = "七年级"
    textbook_version: str = "北师大版（2026）"
    chapter: str = "有理数的加减运算"
    lesson_title: str | None = None
    difficulty_mix: dict[str, int] = Field(default_factory=lambda: {"easy": 2, "medium": 2, "hard": 1})
    exam_count: int = 8
    use_llm: bool = True


class SlidePatch(BaseModel):
    title: str | None = None
    bullets: list[str] | None = None
    script: SlideScript | None = None
    exam_anchor_ids: list[str] | None = None


class ClassroomCreateRequest(BaseModel):
    lesson_id: str


class ClassroomJoinRequest(BaseModel):
    class_code: str


class AdvanceRequest(BaseModel):
    include_quiz: bool = False


class AskRequest(BaseModel):
    question: str
    image_base64: str | None = None


class QuizCreateRequest(BaseModel):
    session_id: str
    slide_id: str | None = None
    mode: Literal["class", "individual"] = "class"


class QuizAnswer(BaseModel):
    item_id: str
    answer: str


class QuizSubmitRequest(BaseModel):
    answers: list[QuizAnswer]


class SettingsUpdateRequest(BaseModel):
    model_name: str | None = None
    temperature: float | None = None
    use_llm: bool | None = None


class ExportRequest(BaseModel):
    format: Literal["json", "pptx"] = "pptx"


class ApiResponse(BaseModel):
    ok: bool = True
    data: Any = None
    message: str = ""
