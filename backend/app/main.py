"""FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import face_analysis, interviews, transcription, ws
from app.core.config import get_settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialised (%s)", settings.DATABASE_URL)
    if settings.LLM_MOCK_MODE or not settings.GROQ_API_KEY:
        logger.warning(
            "LLM is running in TEMPORARY DEVELOPMENT MOCK mode. "
            "Set GROQ_API_KEY and LLM_MOCK_MODE=false for real LLM output."
        )
    yield


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
