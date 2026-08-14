"""Speech-to-text service.

Two providers behind a small interface so callers never change:

- "groq" (default): hosted Whisper API (whisper-large-v3-turbo) — free, fast,
  no local model, and ideal for small/free hosts (e.g. Render 512 MB).
- "local": faster-whisper running on this machine (heavier, but no external call).
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SpeechToTextError(Exception):
    """Raised when transcription cannot be produced from the supplied audio."""


class SpeechToTextService:
    def __init__(self, settings: Settings | None = None) -> None:
        from app.core.config import get_settings

        self.settings = settings or get_settings()
        self._model = None
        self._groq_client = None
        self._lock = threading.Lock()
        self._load_error: str | None = None

    @property
    def provider(self) -> str:
        return self.settings.STT_PROVIDER.lower()

    # ------------------------------------------------------------------
    def _load_model(self):
        """No-op for the Groq provider; lazy-loads faster-whisper for "local"."""
        if self.provider == "groq":
            return None
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from faster_whisper import WhisperModel

                logger.info(
                    "Loading Whisper model '%s' on %s (%s)...",
                    self.settings.WHISPER_MODEL,
                    self.settings.WHISPER_DEVICE,
                    self.settings.WHISPER_COMPUTE_TYPE,
                )
                self._model = WhisperModel(
                    self.settings.WHISPER_MODEL,
                    device=self.settings.WHISPER_DEVICE,
                    compute_type=self.settings.WHISPER_COMPUTE_TYPE,
                )
            except Exception as exc:  # model download failure, missing native libs, etc.
                self._load_error = str(exc)
                logger.error("Failed to load Whisper model: %s", exc)
                raise SpeechToTextError(
                    "Speech-to-text engine could not be initialised. "
                    "Check WHISPER_MODEL and that faster-whisper native dependencies are available."
                ) from exc
        return self._model

    # ------------------------------------------------------------------
    def transcribe(self, audio_bytes: bytes) -> dict:
        """Transcribe raw audio bytes (wav/mp3/ogg/webm). Returns text + metadata."""
        if not audio_bytes:
            raise SpeechToTextError("Empty audio payload.")

        suffix = self._detect_suffix(audio_bytes)
        if suffix is None:
            raise SpeechToTextError("Unsupported audio format. Provide wav/mp3/m4a/ogg/webm.")

        if self.provider == "groq":
            return self._transcribe_groq(audio_bytes, suffix)
        return self._transcribe_local(audio_bytes, suffix)

    # ------------------------------------------------------------------
    def _transcribe_groq(self, audio_bytes: bytes, suffix: str) -> dict:
        client = self._groq_client()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                transcription = client.audio.transcriptions.create(
                    model=self.settings.GROQ_WHISPER_MODEL,
                    file=(f"audio{suffix}", audio_bytes),
                    response_format="verbose_json",
                )
                text = (transcription.text or "").strip()
                if not text:
                    raise SpeechToTextError("No speech detected in the audio (silence).")
                duration = None
                if getattr(transcription, "segments", None):
                    duration = transcription.segments[-1].end
                return {
                    "text": text,
                    "language": getattr(transcription, "language", None),
                    "duration": duration,
                }
            except SpeechToTextError:
                raise
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                message = str(exc).lower()
                is_rate_limit = status == 429 or "rate_limit_exceeded" in message
                if is_rate_limit and attempt < 2:
                    wait = 2**attempt
                    logger.warning(
                        "Groq Whisper rate limit hit; retrying in %ss (%s/2).", wait, attempt + 1
                    )
                    time.sleep(wait)
                    continue
                last_error = exc
                break
        logger.error("Groq transcription failed: %s", last_error)
        raise SpeechToTextError(f"Transcription failed: {last_error}") from last_error

    def _groq_client(self):
        if self._groq_client is not None:
            return self._groq_client
        with self._lock:
            if self._groq_client is not None:
                return self._groq_client
            from groq import Groq

            if not self.settings.GROQ_API_KEY:
                raise SpeechToTextError(
                    "GROQ_API_KEY is required when STT_PROVIDER=groq."
                )
            self._groq_client = Groq(api_key=self.settings.GROQ_API_KEY)
        return self._groq_client

    # ------------------------------------------------------------------
    def _transcribe_local(self, audio_bytes: bytes, suffix: str) -> dict:
        model = self._load_model()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)
        try:
            # vad_filter skips non-speech regions so silence yields an empty
            # transcript instead of hallucinated text on near-silent audio.
            segments, info = model.transcribe(str(tmp_path), beam_size=5, vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if not text:
                raise SpeechToTextError("No speech detected in the audio (silence).")
            return {
                "text": text,
                "language": getattr(info, "language", None),
                "duration": getattr(info, "duration", None),
            }
        except SpeechToTextError:
            raise
        except Exception as exc:
            logger.error("Transcription failed: %s", exc)
            raise SpeechToTextError(f"Transcription failed: {exc}") from exc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _detect_suffix(data: bytes) -> str | None:
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return ".wav"
        if data[:3] == b"ID3" or (data[:2] == b"\xff\xfb"):
            return ".mp3"
        if data[:4] in (b"\x1aE\xdf\xa3",):
            return ".webm"
        if data[:4] == b"fLaC":
            return ".flac"
        if data[4:8] == b"ftyp":
            return ".m4a"
        if data[:2] == b"\xff\xf1" or data[:2] == b"\xff\xf9":
            return ".aac"
        if data[:8] == b"OggS":
            return ".ogg"
        return None


_stt_instance: SpeechToTextService | None = None
_stt_lock = threading.Lock()


def get_stt_service() -> SpeechToTextService:
    global _stt_instance
    if _stt_instance is None:
        with _stt_lock:
            if _stt_instance is None:
                _stt_instance = SpeechToTextService()
    return _stt_instance
