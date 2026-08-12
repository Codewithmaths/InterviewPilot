"""Speech-to-text service using Faster-Whisper (local, open source).

The implementation is isolated behind a small interface so it can later be
replaced by a dedicated transcription service without touching callers.
"""
from __future__ import annotations

import tempfile
import threading
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
        self._lock = threading.Lock()
        self._load_error: str | None = None

    # ------------------------------------------------------------------
    def _load_model(self):
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

        model = self._load_model()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)
        try:
            segments, info = model.transcribe(str(tmp_path), beam_size=5)
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
