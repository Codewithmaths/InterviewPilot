"""Transcription endpoint: accepts an audio upload and returns transcript text."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.core.logging import get_logger
from app.services.stt import SpeechToTextError, get_stt_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["transcription"])

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("/transcription")
async def transcribe_audio(audio: UploadFile) -> dict:
    data = await audio.read()
    if len(data) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio file")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Audio exceeds {MAX_AUDIO_BYTES // (1024 * 1024)}MB limit",
        )
    service = get_stt_service()
    try:
        result = await _run_transcription(service, data)
    except SpeechToTextError as exc:
        logger.warning("Transcription failed: %s", exc)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return {"text": result["text"], "language": result.get("language"), "duration": result.get("duration")}


async def _run_transcription(service, data: bytes) -> dict:
    from fastapi.concurrency import run_in_threadpool

    return await run_in_threadpool(service.transcribe, data)
