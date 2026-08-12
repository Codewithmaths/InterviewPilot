from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.schemas.llm import QuestionBatch
from app.services.llm import LLMError, LLMService, _extract_json_object


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
