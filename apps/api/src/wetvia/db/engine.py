"""Async engine for the application. The URL is passed in; this module does not read the env."""

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

DbStatus = Literal["ok", "error"]


def create_db_engine(database_url: str) -> AsyncEngine:
    """Create a lazy async engine. The URL is not included in errors."""
    if not database_url.startswith("postgresql+psycopg"):
        raise ValueError("expected a postgresql+psycopg database URL")
    return create_async_engine(database_url, pool_pre_ping=True)


async def database_status(engine: AsyncEngine) -> DbStatus:
    """Return ``ok`` when ``SELECT 1`` succeeds.

    Failures are not logged: the exception text can contain the database URL.
    """
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return "error"
    return "ok"
