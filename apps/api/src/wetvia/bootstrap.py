"""Composition root. This is the only module that constructs ``Settings``."""

from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.config import Settings
from wetvia.db import create_db_engine, create_session_factory, database_status
from wetvia.db.engine import DbStatus
from wetvia.llm.adapters.ollama import OllamaProvider
from wetvia.llm.adapters.openai_compat import OpenAICompatProvider
from wetvia.llm.ports import LLMProvider


def package_version() -> str:
    try:
        return version("wetvia-api")
    except PackageNotFoundError:
        return "0.0.0"


def get_provider(settings: Settings) -> LLMProvider:
    """Build the configured adapter. This is the only place that reads LLM settings."""
    if settings.llm_provider == "ollama":
        return OllamaProvider(base_url=settings.llm_base_url, model=settings.llm_model)
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
        raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER is openai_compat")
    api_key = settings.llm_api_key.get_secret_value()
    return OpenAICompatProvider(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=api_key,
    )


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
    app.state.llm = get_provider(loaded)
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    global _app
    if name == "app":
        if _app is None:
            _app = build_app()
        return _app
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
