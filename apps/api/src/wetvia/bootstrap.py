"""Composition root. This is the only module that constructs ``Settings``."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.config import Settings
from wetvia.db import create_db_engine, create_session_factory, database_status
from wetvia.db.engine import DbStatus


def package_version() -> str:
    try:
        return version("wetvia-api")
    except PackageNotFoundError:
        return "0.0.0"


def build_app(settings: Settings | None = None) -> FastAPI:
    loaded = settings if settings is not None else Settings()
    engine = create_db_engine(loaded.database_url)

    async def check_db() -> DbStatus:
        return await database_status(engine)

    async def shutdown() -> None:
        await engine.dispose()

    context = HealthContext(
        llm_provider=loaded.llm_provider,
        version=package_version(),
        check_db=check_db,
    )
    app = create_app(context, shutdown=shutdown)
    app.state.session_factory = create_session_factory(engine)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return build_app()
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
