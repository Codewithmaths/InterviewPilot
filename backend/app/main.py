"""FastAPI application entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import face_analysis, interviews, transcription, ws
from app.core.config import get_settings
from app.core.database import db_display_url, init_db
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


async def _warm_up_ml_models() -> None:
    """Pre-load Whisper and MediaPipe models so the first live request is fast.

    Failures are non-fatal: services fall back to lazy loading on first use.
    """
    from app.services.face import get_face_service
    from app.services.stt import get_stt_service

    logger.info("Pre-loading ML models (Whisper + MediaPipe FaceMesh)...")
    try:
        await asyncio.to_thread(get_stt_service()._load_model)
        logger.info("Whisper model loaded.")
    except Exception as exc:
        logger.warning("Whisper warm-up failed (will load on demand): %s", exc)
    try:
        await asyncio.to_thread(get_face_service()._load_face_mesh)
        logger.info("MediaPipe FaceMesh loaded.")
    except Exception as exc:
        logger.warning("FaceMesh warm-up failed (will load on demand): %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised (%s)", db_display_url(settings.DATABASE_URL))
    if settings.LLM_MOCK_MODE or not settings.GROQ_API_KEY:
        logger.warning(
            "LLM is running in TEMPORARY DEVELOPMENT MOCK mode. "
            "Set GROQ_API_KEY and LLM_MOCK_MODE=false for real LLM output."
        )
    warmup_task: asyncio.Task | None = None
    if settings.ML_MODEL_WARMUP:
        warmup_task = asyncio.create_task(_warm_up_ml_models())
    yield
    if warmup_task is not None:
        warmup_task.cancel()


app = FastAPI(
    title="InterviewPilot",
    description=(
        "Real-time AI-powered interview platform: LLM question generation, "
        "speech-to-text, answer evaluation, facial-analysis cues, WebRTC video "
        "and WebSocket events."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interviews.router)
app.include_router(transcription.router)
app.include_router(face_analysis.router)
app.include_router(ws.router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "llm_mode": "mock" if settings.LLM_MOCK_MODE or not settings.GROQ_API_KEY else "groq",
        "model": settings.GROQ_MODEL,
    }
