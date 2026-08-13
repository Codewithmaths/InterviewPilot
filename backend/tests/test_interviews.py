from __future__ import annotations

import pytest

from .conftest import FakeLLM


def test_create_retrieve_and_role_safe_questions(client, llm_factory):
    llm = llm_factory(FakeLLM())
    response = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Test Candidate",
            "candidate_email": "candidate@example.com",
            "interview_type": "Python",
            "difficulty": "Medium",
            "num_questions": 20,
        },
    )

    assert response.status_code == 201
    interview = response.json()
    assert interview["main_questions_count"] == 20
    assert interview["total_questions_asked"] == 0
    assert interview["join_url"].startswith("http://127.0.0.1:5173/candidate/")
    assert llm.calls["questions"] == 1

    questions = client.get(f"/api/interviews/{interview['id']}/questions")
    assert questions.status_code == 200
    assert len(questions.json()) == 20
    assert "expected_answer" in questions.json()[0]

    candidate_questions = client.get(
        f"/api/interviews/{interview['id']}/candidate/questions"
    )
    assert candidate_questions.status_code == 200
    assert len(candidate_questions.json()) == 20
    assert "expected_answer" not in candidate_questions.json()[0]


@pytest.mark.parametrize(
    "payload",
    [
        {"candidate_name": "A", "candidate_email": "bad", "num_questions": 20},
        {"candidate_name": "A", "candidate_email": "a@example.com", "num_questions": 19},
        {"candidate_name": "A", "candidate_email": "a@example.com", "num_questions": 31},
    ],
)
def test_create_validation(client, llm_factory, payload):
    llm_factory(FakeLLM())
    response = client.post("/api/interviews", json=payload)
    assert response.status_code == 422


def test_groq_rate_limit_is_reported_as_user_friendly_error(client, llm_factory):
    from app.services.llm import LLMRateLimitError

    class RateLimitedLLM:
        def generate_questions(self, **kwargs):
            raise LLMRateLimitError("Groq rate limit reached")

    llm_factory(RateLimitedLLM())
    response = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Rate Limited Candidate",
            "candidate_email": "rate-limit@example.com",
            "interview_type": "Python",
            "difficulty": "Medium",
            "num_questions": 20,
        },
    )

    assert response.status_code == 429
    assert "rate limit" in response.json()["detail"].lower()
    assert "Internal Server Error" not in response.text


def test_lifecycle_state_machine_rejects_invalid_next(client, created_interview):
    interview_id = created_interview["id"]
    started = client.post(f"/api/interviews/{interview_id}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "RUNNING"
    assert started.json()["current_question_index"] == 1

    next_question = client.post(f"/api/interviews/{interview_id}/question/next")
    assert next_question.status_code == 200
    assert next_question.json()["question_number"] == 2

    state = client.post(
        f"/api/interviews/{interview_id}/state",
        json={"to_state": "WAITING_FOR_ANSWER"},
    )
    assert state.status_code == 200
    assert state.json()["state"] == "WAITING_FOR_ANSWER"

    invalid_end_state = client.post(
        f"/api/interviews/{interview_id}/state",
        json={"to_state": "CREATED"},
    )
    assert invalid_end_state.status_code == 409
