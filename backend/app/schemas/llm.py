"""Internal Pydantic schemas that validate structured LLM output."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Classification = Literal["Correct", "Incorrect", "Partially Correct", "Not Confirmed"]


class QuestionDraft(BaseModel):
    question_number: int = Field(ge=1)
    question: str = Field(min_length=3)
    expected_answer: str = Field(min_length=3)
    topic: str = Field(min_length=1)
    difficulty: str = Field(pattern=r"^(Easy|Medium|Hard)$")


class QuestionBatch(BaseModel):
    questions: list[QuestionDraft] = Field(min_length=1)


class EvaluationResult(BaseModel):
    classification: Classification
    score: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    missing_concepts: list[str] = Field(default_factory=list)
    follow_up_required: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)


class FollowUpBatch(BaseModel):
    follow_up_questions: list[str] = Field(min_length=1)


class ReportSection(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    recommended_study_areas: list[str] = Field(default_factory=list)
    summary_note: str = Field(default="")


class ReportBatch(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_concepts: list[str] = Field(default_factory=list)
    recommended_study_areas: list[str] = Field(default_factory=list)
    summary_note: str = Field(default="")
