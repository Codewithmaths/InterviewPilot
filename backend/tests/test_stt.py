"""Tests for the speech-to-text service (Groq Whisper provider)."""
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.stt import SpeechToTextError, SpeechToTextService


def _settings(**overrides) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://u:p@db:5432/postgres",
        "GROQ_API_KEY": "test-key",
        "STT_PROVIDER": "groq",
    }
    base.update(overrides)
    return Settings(**base)


class FakeTranscription:
    text = "Hello world"
    language = "en"
    segments = [SimpleNamespace(start=0.0, end=2.5)]


class FakeAudioTranscriptions:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeGroqClient:
    def __init__(self, result):
        self.audio = SimpleNamespace(transcriptions=FakeAudioTranscriptions(result))


def test_groq_transcribe_returns_text_and_metadata():
    service = SpeechToTextService(_settings())
    fake = FakeGroqClient(FakeTranscription())
    service._groq_client = lambda: fake

    wav = b"RIFF\x00\x00\x00\x00WAVEfmt "
    result = service.transcribe(wav)

    assert result == {"text": "Hello world", "language": "en", "duration": 2.5}
    call = fake.audio.transcriptions.calls[0]
    assert call["model"] == "whisper-large-v3-turbo"
    assert call["response_format"] == "verbose_json"
    assert call["file"][0] == "audio.wav"
    assert call["file"][1] == wav


def test_groq_silence_raises_error():
    service = SpeechToTextService(_settings())
    service._groq_client = lambda: FakeGroqClient(SimpleNamespace(text="  ", language="en"))

    with pytest.raises(SpeechToTextError, match="No speech detected"):
        service.transcribe(b"RIFF\x00\x00\x00\x00WAVEfmt ")


class _RateLimitError(Exception):
    status_code = 429


def test_groq_retries_on_rate_limit_then_succeeds():
    service = SpeechToTextService(_settings())
    rate_error = _RateLimitError()
    attempts = []

    def flaky_create(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise rate_error
        return FakeTranscription()

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=flaky_create)))
    service._groq_client = lambda: client

    result = service.transcribe(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert result["text"] == "Hello world"
    assert len(attempts) == 2


def test_groq_raises_when_key_missing():
    service = SpeechToTextService(_settings(GROQ_API_KEY=""))
    service._groq_client = lambda: (_ for _ in ()).throw(
        SpeechToTextError("GROQ_API_KEY is required when STT_PROVIDER=groq.")
    )
    with pytest.raises(SpeechToTextError, match="GROQ_API_KEY"):
        service._groq_client()


def test_groq_provider_skips_local_model_load():
    service = SpeechToTextService(_settings())
    assert service.provider == "groq"
    assert service._load_model() is None


def test_local_provider_load_failure_raises_stt_error(monkeypatch):
    service = SpeechToTextService(_settings(STT_PROVIDER="local"))

    def boom(self):
        raise SpeechToTextError("Speech-to-text engine could not be initialised.")

    monkeypatch.setattr(SpeechToTextService, "_load_model", boom)
    with pytest.raises(SpeechToTextError):
        service._transcribe_local(b"RIFF\x00\x00\x00\x00WAVEfmt ", ".wav")
