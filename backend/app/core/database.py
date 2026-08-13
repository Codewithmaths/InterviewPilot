"""Database engine, session factory and declarative base."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

DB_URL = settings.DATABASE_URL
IS_SQLITE = DB_URL.startswith("sqlite")
IS_POSTGRES = DB_URL.startswith("postgresql")

# Keep a single persistent in-memory connection when SQLite in-memory is requested.
connect_args = {"check_same_thread": False} if IS_SQLITE else {}
if IS_POSTGRES and settings.DATABASE_SSLMODE:
    connect_args["sslmode"] = settings.DATABASE_SSLMODE

engine_options: dict = {"pool_pre_ping": True, "future": True}
if not IS_SQLITE:
    engine_options["pool_size"] = settings.DATABASE_POOL_SIZE
    engine_options["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

engine = create_engine(DB_URL, connect_args=connect_args, **engine_options)

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
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """Best-effort column additions for databases created by older versions.

    create_all() never alters existing tables, so columns added to the models
    later need an explicit ALTER TABLE. Safe to skip for non-SQLite backends.
    """
    if not DB_URL.startswith("sqlite"):
        return
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "evaluations" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("evaluations")}
    if "metric_scores" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE evaluations ADD COLUMN metric_scores JSON"))
