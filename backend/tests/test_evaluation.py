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

    # A second fetch is served straight from the database — no LLM call.
    cached = client.get(f"/api/interviews/{interview_id}/report")
    assert cached.status_code == 200, cached.text
    assert cached.json()["counts"]["Partially Correct"] == 1
    assert llm.calls["reports"] == 1

    # refresh=true regenerates and overwrites the stored report.
    refreshed = client.get(f"/api/interviews/{interview_id}/report?refresh=true")
    assert refreshed.status_code == 200, refreshed.text
    assert llm.calls["reports"] == 2


def test_multiple_followups_can_be_asked_in_sequence(client, llm_factory):
    """Regression: selecting a 2nd/3rd follow-up must not fail with
    'No pending follow-ups in the current state'."""
    llm_factory(FakeLLM())
    created = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Followup Candidate",
            "candidate_email": "followup@example.com",
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
        json={"question_id": question["id"], "transcript": "A partial answer.", "duration_seconds": 30},
    )
    assert answer.status_code == 200, answer.text

    followups = client.get(f"/api/interviews/{interview_id}/followups").json()
    assert len(followups) == 3

    # Ask and answer follow-ups one by one; every select must succeed.
    for fu in followups:
        selected = client.post(f"/api/interviews/{interview_id}/followups/{fu['id']}/select")
        assert selected.status_code == 200, selected.text
        answered = client.post(
            f"/api/interviews/{interview_id}/followups/{fu['id']}/answer",
            json={"followup_id": fu["id"], "transcript": "Follow-up answer.", "duration_seconds": 15},
        )
        assert answered.status_code == 200, answered.text

    # Re-selecting an already answered follow-up is rejected.
    reselect = client.post(f"/api/interviews/{interview_id}/followups/{followups[0]['id']}/select")
    assert reselect.status_code == 409

    # All follow-ups answered: the main flow resumes and next question works.
    after = client.get(f"/api/interviews/{interview_id}/followups").json()
    assert all(f["answered"] for f in after)
    nxt = client.post(f"/api/interviews/{interview_id}/question/next")
    assert nxt.status_code == 200, nxt.text


def test_next_question_allowed_while_followups_pending(client, llm_factory):
    """The interviewer may skip remaining follow-ups and move on."""
    llm_factory(FakeLLM())
    created = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Skip Candidate",
            "candidate_email": "skip@example.com",
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
        json={"question_id": question["id"], "transcript": "A partial answer.", "duration_seconds": 30},
    )
    assert answer.status_code == 200, answer.text

    # Follow-ups are pending but unanswered; moving to the next question works.
    nxt = client.post(f"/api/interviews/{interview_id}/question/next")
    assert nxt.status_code == 200, nxt.text


def test_all_allowed_classifications_are_schema_valid():
    from app.schemas.llm import EvaluationResult

    for classification in ("Correct", "Incorrect", "Partially Correct", "Not Confirmed"):
        result = EvaluationResult(
            classification=classification,
            score=0.5,
            reason="Evidence-based reason.",
        )
        assert result.classification == classification


def test_question_type_metrics_are_returned_and_persisted(client, llm_factory):
    """Evaluation carries question-type-aware metric scores through the whole
    pipeline: API response, history, and the final report."""
    llm_factory(FakeLLM())
    created = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Metrics Candidate",
            "candidate_email": "metrics@example.com",
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
        json={"question_id": question["id"], "transcript": "A partial answer.", "duration_seconds": 30},
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert len(body["metrics"]) == 3
    names = [m["name"] for m in body["metrics"]]
    assert "Accuracy" in names and "Completeness" in names
    assert all(0.0 <= m["score"] <= 1.0 for m in body["metrics"])

    history = client.get(f"/api/interviews/{interview_id}/history").json()["items"]
    assert history[0]["answers"][0]["evaluation"]["metrics"][0]["name"] == "Accuracy"

    ended = client.post(f"/api/interviews/{interview_id}/end")
    assert ended.status_code == 200
    report = client.get(f"/api/interviews/{interview_id}/report").json()
    qa = report["question_analysis"][0]
    assert qa["metrics"][0]["name"] == "Accuracy"
    assert qa["metrics"][0]["score"] == 0.7


def test_skip_question_advances_and_records_event(client, llm_factory):
    llm_factory(FakeLLM())
    created = client.post(
        "/api/interviews",
        json={
            "candidate_name": "Skip Candidate",
            "candidate_email": "skip2@example.com",
            "interview_type": "Python",
            "difficulty": "Medium",
            "num_questions": 20,
        },
    ).json()
    interview_id = created["id"]
    assert client.post(f"/api/interviews/{interview_id}/start").status_code == 200
    first = client.get(f"/api/interviews/{interview_id}/questions").json()[0]

    skipped = client.post(f"/api/interviews/{interview_id}/question/skip")
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["question_number"] == 2

    # No answer/evaluation was produced for the skipped question.
    history = client.get(f"/api/interviews/{interview_id}/history").json()["items"]
    assert history[0]["answers"] == []

    # Skip from the last question reports no more questions.
    last_number = client.get(f"/api/interviews/{interview_id}/questions").json()[-1]["question_number"]
    client.post(f"/api/interviews/{interview_id}/question/{last_number}")
    no_more = client.post(f"/api/interviews/{interview_id}/question/skip")
    assert no_more.status_code == 404

    # The report counts the skipped question and labels it in the analysis.
    ended = client.post(f"/api/interviews/{interview_id}/end")
    assert ended.status_code == 200
    report = client.get(f"/api/interviews/{interview_id}/report").json()
    assert report["counts"]["Skipped"] == 1
    skipped_item = next(
        (q for q in report["question_analysis"] if q["question_number"] == 1), None
    )
    assert skipped_item is not None
    assert skipped_item["classification"] == "Skipped"
