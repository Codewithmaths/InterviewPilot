from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.schemas.llm import QuestionBatch
from app.services.llm import (
    LLMError,
    LLMRateLimitError,
    LLMService,
    _extract_json_object,
    _retry_after_seconds,
)


def test_extract_json_from_markdown_fence():
    assert _extract_json_object('```json\n{"questions": []}\n```') == {"questions": []}


def test_invalid_structured_output_retries_once():
    class FakeCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"bad": true}'))]
            )

    completions = FakeCompletions()
    service = LLMService(Settings(GROQ_API_KEY="test-key"))
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with pytest.raises(LLMError):
        service._chat_json("system", "user", QuestionBatch, retries=1)
    assert completions.calls == 2


def _rate_limit_error(retry_after: str = "0.01") -> Exception:
    response = SimpleNamespace(headers={"retry-after": retry_after})
    exc = Exception("rate_limit_exceeded")
    exc.status_code = 429
    exc.response = response
    return exc


def test_rate_limit_waits_and_recovers(monkeypatch):
    monkeypatch.setattr("app.services.llm.time.sleep", lambda seconds: None)
    valid = (
        '{"questions": [{"question_number": 1, "question": "Sample question?", '
        '"expected_answer": "Sample answer.", "topic": "Python", "difficulty": "Medium"}]}'
    )

    class FlakyCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise _rate_limit_error()
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=valid))]
            )

    completions = FlakyCompletions()
    service = LLMService(Settings(GROQ_API_KEY="test-key"))
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    data = service._chat_json("system", "user", QuestionBatch)
    assert data["questions"][0]["question"] == "Sample question?"
    assert completions.calls == 3


def test_rate_limit_raises_after_exhausting_retries(monkeypatch):
    monkeypatch.setattr("app.services.llm.time.sleep", lambda seconds: None)

    class AlwaysLimitedCompletions:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            raise _rate_limit_error()

    completions = AlwaysLimitedCompletions()
    service = LLMService(Settings(GROQ_API_KEY="test-key"))
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

    with pytest.raises(LLMRateLimitError):
        service._chat_json("system", "user", QuestionBatch)
    assert completions.calls == 4  # initial attempt + 3 rate-limit retries


def test_retry_after_seconds_parsing():
    assert _retry_after_seconds(Exception("no headers")) == 5.0  # fallback default
    exc = _rate_limit_error("2.5")
    assert _retry_after_seconds(exc) == 2.5
    exc_minutes = _rate_limit_error("1m2s")
    assert _retry_after_seconds(exc_minutes) == 30.0  # capped at RATE_LIMIT_MAX_WAIT_SECONDS
