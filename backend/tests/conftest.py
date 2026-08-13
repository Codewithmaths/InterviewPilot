"""Shared fixtures: isolated test database, app client, mocked LLM."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base, get_db
from app.schemas.llm import EvaluationResult, QuestionBatch, ReportSection
from app.services import evaluation as eval_service_mod
from app.services import interview as interview_service_mod
from app.services import report as report_service_mod

TEST_QUESTIONS = [
    {
        "question_number": i + 1,
        "question": f"Mock question {i + 1} about Python?",
        "expected_answer": f"Reference answer for question {i + 1}.",
        "topic": "Python",
        "difficulty": "Medium",
    }
    for i in range(20)
]


class FakeLLM:
    """Deterministic LLM double used in unit tests. No Groq calls."""

    def __init__(self, classification: str = "Partially Correct") -> None:
        self.classification = classification
        self.calls = {"questions": 0, "evaluations": 0, "followups": 0, "reports": 0}

    def generate_questions(self, interview_type, difficulty, num_questions, candidate_name, job_description=None):
        self.calls["questions"] += 1
        return QuestionBatch.model_validate(
            {"questions": TEST_QUESTIONS[:num_questions]}
        )

    def evaluate_answer(self, question, topic, difficulty, expected_answer, candidate_answer):
        self.calls["evaluations"] += 1
        if self.classification == "Correct":
            return EvaluationResult(
                classification="Correct", score=0.9, reason="Solid answer.",
                missing_concepts=[], metrics=[
                    {"name": "Accuracy", "score": 0.9},
                    {"name": "Completeness", "score": 0.9},
                ],
                follow_up_required=False, follow_up_questions=[],
            )
        if self.classification == "Incorrect":
            return EvaluationResult(
                classification="Incorrect", score=0.2, reason="Misunderstood the concept.",
                missing_concepts=["Core concept"], metrics=[
                    {"name": "Accuracy", "score": 0.2},
                    {"name": "Completeness", "score": 0.2},
                ],
                follow_up_required=False, follow_up_questions=[],
            )
        if self.classification == "Not Confirmed":
            return EvaluationResult(
                classification="Not Confirmed", score=0.0, reason="Insufficient evidence.",
                missing_concepts=[], metrics=[
                    {"name": "Accuracy", "score": 0.0},
                    {"name": "Completeness", "score": 0.0},
                ],
                follow_up_required=False, follow_up_questions=[],
            )
        return EvaluationResult(
            classification="Partially Correct", score=0.55,
            reason="Partial understanding shown.", missing_concepts=["Concept A", "Concept B"],
            metrics=[
                {"name": "Accuracy", "score": 0.7},
                {"name": "Completeness", "score": 0.4},
                {"name": "Clarity", "score": 0.6},
            ],
            follow_up_required=True,
            follow_up_questions=[
                "Follow-up A?",
                "Follow-up B?",
                "Follow-up C?",
            ],
        )

    def generate_followups(self, question, topic, candidate_answer, reason, missing_concepts):
        self.calls["followups"] += 1
        return ["Follow-up A?", "Follow-up B?", "Follow-up C?"]

    def generate_final_report(self, context: str) -> ReportSection:
        self.calls["reports"] += 1
        return ReportSection(
            strengths=["Good communication"],
            weaknesses=["Missing depth in Python"],
            missing_concepts=["Concept A"],
            recommended_study_areas=["Review Concept A"],
            summary_note="AI-assisted estimate, not a definitive hiring decision.",
        )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def llm_factory(monkeypatch):
    """Make InterviewService/EvaluationService/ReportService use FakeLLM."""
    def _apply(fake: FakeLLM):
        def make(db, llm=None):
            return fake

        monkeypatch.setattr(interview_service_mod, "LLMService", lambda settings=None: fake)
        monkeypatch.setattr(eval_service_mod, "LLMService", lambda settings=None: fake)
        monkeypatch.setattr(report_service_mod, "LLMService", lambda settings=None: fake)
        return fake

    return _apply


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app

    test_db = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(test_db, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def created_interview(client, llm_factory):
    llm_factory(FakeLLM())
    r = client.post("/api/interviews", json={
        "candidate_name": "Test Candidate",
        "candidate_email": "candidate@example.com",
        "interview_type": "Python",
        "difficulty": "Medium",
        "num_questions": 20,
    })
    assert r.status_code == 201, r.text
    return r.json()
