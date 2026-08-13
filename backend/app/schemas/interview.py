"""Pydantic schemas for request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator

InterviewType = Literal[
    "Technical",
    "HR",
    "Behavioral",
    "Python",
    "Machine Learning",
    "Data Science",
    "SQL",
    "Software Engineering",
    "Custom",
]
Difficulty = Literal["Easy", "Medium", "Hard"]
Classification = Literal["Correct", "Incorrect", "Partially Correct", "Not Confirmed"]


class CandidateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


class InterviewCreate(BaseModel):
    candidate_name: str = Field(..., min_length=1, max_length=200)
    candidate_email: EmailStr
    interview_type: InterviewType = "Technical"
    difficulty: Difficulty = "Medium"
    num_questions: int = Field(20, ge=20, le=30)
    job_description: str | None = Field(None, max_length=10000)


class InterviewUpdate(BaseModel):
    job_description: str | None = None


class AnswerCreate(BaseModel):
    question_id: int | None = None
    followup_id: int | None = None
    transcript: str = Field(..., min_length=1)
    duration_seconds: int | None = None

    @field_validator("transcript")
    @classmethod
    def strip_transcript(cls, v: str) -> str:
        return v.strip()

    def model_post_init(self, __context) -> None:
        if self.question_id is None and self.followup_id is None:
            raise ValueError("Either question_id or followup_id must be provided")
        if self.question_id is not None and self.followup_id is not None:
            raise ValueError("Provide only one of question_id or followup_id")


class FollowUpSelect(BaseModel):
    followup_id: int


class FollowUpAnswerCreate(BaseModel):
    transcript: str = Field(..., min_length=1)
    duration_seconds: int | None = None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_number: int
    question: str
    expected_answer: str
    topic: str
    difficulty: str


class CandidateQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_number: int
    question: str
    topic: str
    difficulty: str


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    classification: Classification
    score: float
    reason: str
    missing_concepts: list[str]
    metrics: list[dict] = Field(
        default_factory=list,
        validation_alias=AliasChoices("metrics", "metric_scores"),
    )
    follow_up_required: bool
    follow_up_questions: list[str]


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int | None
    followup_id: int | None
    is_followup: bool
    transcript: str
    duration_seconds: int | None
    created_at: datetime
    evaluation: EvaluationOut | None = None


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    followup_number: int
    text: str


class FaceEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    face_detected: bool
    category: str
    confidence: float
    timestamp: datetime


class InterviewSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_name: str
    candidate_email: str
    interview_type: str
    difficulty: str
    num_questions: int
    job_description: str | None
    status: str
    room_code: str
    join_url: str | None
    current_question_index: int | None
    main_questions_count: int
    follow_up_questions_count: int
    total_questions_asked: int
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None


def interview_to_summary(interview) -> "InterviewSummary":
    """Build a summary from an ORM Interview (traversing the candidate relation)."""
    candidate = interview.candidate
    return InterviewSummary(
        id=interview.id,
        candidate_name=candidate.name if candidate else "",
        candidate_email=candidate.email if candidate else "",
        interview_type=interview.interview_type,
        difficulty=interview.difficulty,
        num_questions=interview.num_questions,
        job_description=interview.job_description,
        status=interview.status,
        room_code=interview.room_code,
        join_url=interview.join_url,
        current_question_index=interview.current_question_index,
        main_questions_count=interview.main_questions_count,
        follow_up_questions_count=interview.follow_up_questions_count,
        total_questions_asked=interview.total_questions_asked,
        created_at=interview.created_at,
        started_at=interview.started_at,
        ended_at=interview.ended_at,
        duration_seconds=interview.duration_seconds,
    )


class HistoryItem(BaseModel):
    question_number: int | None
    question: str
    expected_answer: str | None
    topic: str | None
    difficulty: str | None
    is_followup: bool
    followup_text: str | None
    answers: list[AnswerOut]


class InterviewHistory(BaseModel):
    items: list[HistoryItem]


class FaceAnalysisRequest(BaseModel):
    image_base64: str = Field(..., min_length=20)


class FaceAnalysisResult(BaseModel):
    face_detected: bool
    category: str
    confidence: float
    timestamp: datetime


class TranscriptionRequest(BaseModel):
    audio_base64: str = Field(..., min_length=20)


class TranscriptionResult(BaseModel):
    text: str
    language: str | None = None
    duration: float | None = None


class ReportSection(BaseModel):
    strengths: list[str]
    weaknesses: list[str]
    missing_concepts: list[str]
    recommended_study_areas: list[str]
    summary_note: str


class QuestionReportItem(BaseModel):
    question_number: int
    question: str
    classification: str
    score: float
    reason: str
    metrics: list[dict] = Field(default_factory=list)
    follow_up_answers: list[dict] = Field(default_factory=list)


class InterviewReport(BaseModel):
    candidate_name: str
    interview_type: str
    difficulty: str
    date: datetime
    duration_seconds: int | None
    main_questions_count: int
    follow_up_questions_count: int
    total_questions_asked: int
    counts: dict[str, int]
    percentages: dict[str, float]
    performance_score: float | None
    scoring_methodology: str
    visual_cue_summary: dict[str, float]
    section: ReportSection
    question_analysis: list[QuestionReportItem]
    generated_at: datetime


class StateTransition(BaseModel):
    from_state: str
    to_state: str
    allowed: bool
