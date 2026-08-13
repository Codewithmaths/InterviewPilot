"""Database engine, session factory and declarative base (Supabase/PostgreSQL)."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
DB_URL = settings.DATABASE_URL

if not DB_URL.startswith("postgresql"):
    raise RuntimeError(
        "InterviewPilot requires a Supabase (PostgreSQL) database. "
        "Set DATABASE_URL to your Supabase connection string."
    )

connect_args: dict = {}
if settings.DATABASE_SSLMODE:
    connect_args["sslmode"] = settings.DATABASE_SSLMODE

engine = create_engine(
    DB_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def db_display_url(url: str) -> str:
    """Mask the password portion of a database URL for safe logging."""
    if "://" in url and "@" in url:
        scheme, rest = url.split("://", 1)
        userinfo, host = rest.rsplit("@", 1)
        user = userinfo.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Imported models must be registered before this call."""
    from app.models import entities  # noqa: F401

    Base.metadata.create_all(bind=engine)
