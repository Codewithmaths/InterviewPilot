"""SQLAlchemy ORM models for the InterviewPilot domain."""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InterviewState(str, enum.Enum):
    CREATED = "CREATED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_ANSWER = "WAITING_FOR_ANSWER"
    TRANSCRIBING = "TRANSCRIBING"
    EVALUATING = "EVALUATING"
    FOLLOW_UP = "FOLLOW_UP"
    NEXT_QUESTION = "NEXT_QUESTION"
    COMPLETED = "COMPLETED"


class Classification(str, enum.Enum):
    CORRECT = "Correct"
    INCORRECT = "Incorrect"
    PARTIALLY_CORRECT = "Partially Correct"
    NOT_CONFIRMED = "Not Confirmed"


class FaceCategory(str, enum.Enum):
    LOW_CONFIDENT = "Low confident"
    NERVOUS = "Nervous"
    CONFIDENT = "Confident"
    ENERGETIC = "Energetic"
    FACE_NOT_DETECTED = "Face Not Detected"


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)

    interview_type: Mapped[str] = mapped_column(String(100), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)
    num_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(InterviewState), default=InterviewState.CREATED, nullable=False
    )

    room_code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    join_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    current_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True
    )
    current_question_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    main_questions_count: Mapped[int] = mapped_column(Integer, default=0)
    follow_up_questions_count: Mapped[int] = mapped_column(Integer, default=0)
    total_questions_asked: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="interviews")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="Question.question_number",
        foreign_keys="Question.interview_id",
    )
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    face_events: Mapped[list["FaceAnalysisEvent"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    events: Mapped[list["InterviewEvent"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    followups: Mapped[list["FollowUpQuestion"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )

    report: Mapped["Report | None"] = relationship(
        back_populates="interview", uselist=False, cascade="all, delete-orphan"
    )

    current_question: Mapped["Question | None"] = relationship(
        foreign_keys=[current_question_id]
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), default="General")
    difficulty: Mapped[str] = mapped_column(String(20), default="Medium")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(
        back_populates="questions", foreign_keys=[interview_id]
    )
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
    followups: Mapped[list["FollowUpQuestion"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True, index=True
    )
    followup_id: Mapped[int | None] = mapped_column(
        ForeignKey("followup_questions.id"), nullable=True, index=True
    )
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False)
    transcript: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(back_populates="answers")
    question: Mapped["Question | None"] = relationship(back_populates="answers")
    followup: Mapped["FollowUpQuestion | None"] = relationship(back_populates="answers")
    evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="answer", cascade="all, delete-orphan", uselist=False
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"), index=True)
    classification: Mapped[str] = mapped_column(Enum(Classification), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    missing_concepts: Mapped[list] = mapped_column(JSON, default=list)
    metric_scores: Mapped[list] = mapped_column(JSON, default=list)
    follow_up_required: Mapped[bool] = mapped_column(Boolean, default=False)
    follow_up_questions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    answer: Mapped["Answer"] = relationship(back_populates="evaluation")


class FollowUpQuestion(Base):
    __tablename__ = "followup_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    followup_number: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(back_populates="followups")
    question: Mapped["Question"] = relationship(back_populates="followups")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="followup", cascade="all, delete-orphan"
    )


class FaceAnalysisEvent(Base):
    __tablename__ = "face_analysis_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    face_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(back_populates="face_events")


class InterviewEvent(Base):
    __tablename__ = "interview_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(back_populates="events")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(
        ForeignKey("interviews.id"), unique=True, index=True, nullable=False
    )
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interview: Mapped["Interview"] = relationship(back_populates="report")
