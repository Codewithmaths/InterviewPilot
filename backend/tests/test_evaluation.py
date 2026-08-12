from __future__ import annotations

from .conftest import FakeLLM


def test_answer_followup_history_and_report(client, llm_factory):
    llm = llm_factory(FakeLLM())
    created = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Evaluation Candidate",
            "candidate_email": "evaluation@example.com",
            "interview_type": "Python",
            "difficulty": "Medium",
            "num_questions": 20,
        },
    ).json()
    interview_id = created["id"]
    assert client.post(f"/api/interviews/{interview_id}/start").status_code == 200
    question = client.get(f"/api/interviews/{interview_id}/questions").json()[0]

    answer = client.post(
        f"/api/interviews/{interview_id}/answers",
        json={
            "question_id": question["id"],
            "transcript": "The candidate explains part of the concept.",
            "duration_seconds": 30,
        },
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["classification"] == "Partially Correct"
    assert body["follow_up_required"] is True
    assert len(body["follow_up_questions"]) == 3
    assert llm.calls["evaluations"] == 1

    followups = client.get(f"/api/interviews/{interview_id}/followups").json()
    assert len(followups) == 3
    assert followups[0]["answered"] is False

    selected = client.post(
        f"/api/interviews/{interview_id}/followups/{followups[0]['id']}/select"
    )
    assert selected.status_code == 200
    followup_answer = client.post(
        f"/api/interviews/{interview_id}/followups/{followups[0]['id']}/answer",
        json={
            "followup_id": followups[0]["id"],
            "transcript": "A focused answer to the follow-up.",
            "duration_seconds": 20,
        },
    )
    assert followup_answer.status_code == 200, followup_answer.text

    followups_after = client.get(f"/api/interviews/{interview_id}/followups").json()
    assert followups_after[0]["answered"] is True

    history = client.get(f"/api/interviews/{interview_id}/history").json()["items"]
    assert len(history) == 23
    assert sum(1 for item in history if item["is_followup"]) == 3

    ended = client.post(f"/api/interviews/{interview_id}/end")
    assert ended.status_code == 200
    report = client.get(f"/api/interviews/{interview_id}/report")
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert report_body["counts"]["Partially Correct"] == 1
    assert report_body["follow_up_questions_count"] == 1
    assert report_body["total_questions_asked"] == 2
    assert llm.calls["reports"] == 1


def test_all_allowed_classifications_are_schema_valid():
    from app.schemas.llm import EvaluationResult

    for classification in ("Correct", "Incorrect", "Partially Correct", "Not Confirmed"):
        result = EvaluationResult(
            classification=classification,
            score=0.5,
            reason="Evidence-based reason.",
        )
        assert result.classification == classification
