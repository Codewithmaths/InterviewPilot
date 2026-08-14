"""Application configuration loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> project root (two levels above "app")
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Groq / LLM
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    LLM_MOCK_MODE: bool = False

    # Database — Supabase (PostgreSQL). Required; set to the Supabase
    # "Session pooler" connection string from Project Settings -> Database.
    DATABASE_URL: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError(
                "DATABASE_URL is required. Set it to your Supabase connection string "
                "(Project Settings -> Database -> Connection string -> Session pooler)."
            )
        if not v.startswith("postgresql"):
            raise ValueError(
                "DATABASE_URL must be a postgresql:// connection string. "
                "Supabase is the only supported database."
            )
        return v
    # Postgres/SSL settings (Supabase requires SSL). Only applied to postgres URLs.
    DATABASE_SSLMODE: str = "require"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 10

    # Server
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://127.0.0.1:5173"

    # CORS - comma separated origins
    CORS_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Face analysis
    FACE_ANALYSIS_INTERVAL: float = 1.0

    # Speech-to-text
    # "groq" uses the hosted Whisper API (free, no local model); "local" uses
    # faster-whisper with the settings below. "groq" is the default so the app
    # runs on small/free hosts (Render) without a heavy local model.
    STT_PROVIDER: str = "groq"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"

    # Pre-load Whisper + MediaPipe models at startup (production recommended)
    ML_MODEL_WARMUP: bool = True

    # Logging
    LOG_LEVEL: str = "INFO"

    @field_validator("CORS_ORIGINS")
    @classmethod
    def parse_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.GROQ_API_KEY) and not self.LLM_MOCK_MODE


@lru_cache
def get_settings() -> Settings:
    return Settings()
