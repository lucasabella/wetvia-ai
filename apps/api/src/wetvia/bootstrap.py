"""Composition root. This is the only module that constructs ``Settings``."""

import asyncio
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from threading import Lock

from fastapi import FastAPI

from nl_wetten_ingest import BwbSRUClient
from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.cli import build_cli
from wetvia.config import Settings
from wetvia.db import create_db_engine, create_session_factory, database_status
from wetvia.db.engine import DbStatus
from wetvia.embeddings.adapters.sentence_transformers import SentenceTransformersEmbedder
from wetvia.ingest import EmbeddingJob, IngestService
from wetvia.llm.adapters.ollama import OllamaProvider
from wetvia.llm.adapters.openai_compat import OpenAICompatProvider
from wetvia.llm.ports import LLMProvider
from wetvia.retrieval.adapters.pg import PgHybridRetriever


class _LazyEmbedder:
    """Defer sentence-transformers and its model files until the first search."""

    def __init__(self, model_id: str, dimension: int) -> None:
        self.model_id = model_id
        self.dimension = dimension
        self._adapter: SentenceTransformersEmbedder | None = None
        self._lock = Lock()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        adapter = self._get_adapter()
        return adapter.embed(texts)

    def _get_adapter(self) -> SentenceTransformersEmbedder:
        if self._adapter is None:
            with self._lock:
                if self._adapter is None:
                    self._adapter = SentenceTransformersEmbedder(
                        self.model_id,
                        dimension=self.dimension,
                    )
        return self._adapter


def package_version() -> str:
    try:
        return version("wetvia-api")
    except PackageNotFoundError:
        return "0.0.0"


def get_provider(settings: Settings) -> LLMProvider:
    """Build the configured adapter. This is the only place that reads LLM settings."""
    if settings.llm_provider == "ollama":
        return get_ollama_provider(base_url=settings.llm_base_url, model=settings.llm_model)
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
        raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER is openai_compat")
    api_key = settings.llm_api_key.get_secret_value()
    return OpenAICompatProvider(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=api_key,
    )


def get_ollama_provider(
    *,
    base_url: str,
    model: str,
    num_ctx: int | None = None,
    keep_alive: int | str | None = None,
    think: bool | None = None,
) -> LLMProvider:
    """Build an explicitly configured local provider for tools such as eval."""
    return OllamaProvider(
        base_url=base_url,
        model=model,
        num_ctx=num_ctx,
        keep_alive=keep_alive,
        think=think,
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
    sessions = create_session_factory(engine)
    retriever = PgHybridRetriever(
        sessions,
        _LazyEmbedder(loaded.embedding_model, loaded.embedding_dimension),
    )
    app = create_app(context, retriever=retriever, shutdown=shutdown)
    app.state.session_factory = sessions
    app.state.llm = get_provider(loaded)
    return app


def run_cli(settings: Settings | None = None) -> None:
    """Compose the batch CLI without constructing API or LLM adapters."""
    loaded = settings if settings is not None else Settings()
    engine = create_db_engine(loaded.database_url)
    try:
        with BwbSRUClient() as source:
            session_factory = create_session_factory(engine)

            def create_embedding_job() -> EmbeddingJob:
                embedder = SentenceTransformersEmbedder(
                    loaded.embedding_model,
                    dimension=loaded.embedding_dimension,
                )
                return EmbeddingJob(
                    session_factory,
                    embedder,
                    batch_size=loaded.embedding_batch_size,
                )

            service = IngestService(session_factory, source)
            build_cli(service, create_embedding_job)()
    finally:
        asyncio.run(engine.dispose())


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    global _app
    if name == "app":
        if _app is None:
            _app = build_app()
        return _app
    message = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(message)
