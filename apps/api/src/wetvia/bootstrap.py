"""Composition root. This is the only module that constructs ``Settings``."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from threading import Lock
from types import MappingProxyType
from urllib.parse import urlsplit

from fastapi import FastAPI

from nl_wetten_ingest import BwbSRUClient
from wetvia.answer import AnswerPipeline, Utf8ByteUpperBoundCounter
from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.api.schemas.chat import ChatMode
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
from wetvia.retrieval.ports import Retriever

SCALEWAY_API_BASE_URL = "https://api.scaleway.ai/v1"


@dataclass(frozen=True, slots=True)
class RetrieverRuntime:
    """Public retrieval composition and embedding-space identity for consumers."""

    retriever: Retriever
    model_id: str
    dimension: int


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
    """Build one explicitly selected adapter for legacy consumers and tests."""
    if settings.llm_provider == "ollama":
        if not settings.llm_base_url.strip() or not settings.llm_model.strip():
            raise RuntimeError("local LLM URL and model must be configured")
        return get_ollama_provider(base_url=settings.llm_base_url, model=settings.llm_model)
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
        raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER is openai_compat")
    if (
        not _is_scaleway_endpoint(settings.cloud_llm_base_url)
        or not settings.cloud_llm_model.strip()
    ):
        raise RuntimeError("cloud mode requires the configured Scaleway EU endpoint and model")
    api_key = settings.llm_api_key.get_secret_value()
    return OpenAICompatProvider(
        base_url=SCALEWAY_API_BASE_URL,
        model=settings.cloud_llm_model,
        api_key=api_key,
    )


def get_chat_providers(settings: Settings) -> dict[ChatMode, LLMProvider]:
    """Build the configured local/cloud adapters for per-request selection."""
    providers: dict[ChatMode, LLMProvider] = {}
    if settings.llm_base_url.strip() and settings.llm_model.strip():
        providers["local"] = get_ollama_provider(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    cloud_key = (
        settings.llm_api_key.get_secret_value().strip() if settings.llm_api_key is not None else ""
    )
    if (
        cloud_key
        and _is_scaleway_endpoint(settings.cloud_llm_base_url)
        and settings.cloud_llm_model.strip()
    ):
        providers["cloud"] = OpenAICompatProvider(
            base_url=SCALEWAY_API_BASE_URL,
            model=settings.cloud_llm_model,
            api_key=cloud_key,
        )
    return providers


def _is_scaleway_endpoint(value: str) -> bool:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "api.scaleway.ai"
        and parsed.path.rstrip("/") == "/v1"
        and port in {None, 443}
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
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


@asynccontextmanager
async def open_retriever(settings: Settings | None = None) -> AsyncIterator[RetrieverRuntime]:
    """Compose a date-aware retriever and dispose its database engine on exit.

    Evaluation and other in-process consumers use this public composition API
    instead of importing the PostgreSQL adapter or reading settings directly.
    """
    loaded = settings if settings is not None else Settings()
    engine = create_db_engine(loaded.database_url)
    try:
        sessions = create_session_factory(engine)
        yield RetrieverRuntime(
            retriever=PgHybridRetriever(
                sessions,
                _LazyEmbedder(loaded.embedding_model, loaded.embedding_dimension),
            ),
            model_id=loaded.embedding_model,
            dimension=loaded.embedding_dimension,
        )
    finally:
        await engine.dispose()


def build_app(settings: Settings | None = None) -> FastAPI:
    loaded = settings if settings is not None else Settings()
    engine = create_db_engine(loaded.database_url)

    async def check_db() -> DbStatus:
        return await database_status(engine)

    async def shutdown() -> None:
        await engine.dispose()

    providers = get_chat_providers(loaded)
    context = HealthContext(
        version=package_version(),
        check_db=check_db,
        local_configured="local" in providers,
        cloud_configured="cloud" in providers,
    )
    sessions = create_session_factory(engine)
    retriever = PgHybridRetriever(
        sessions,
        _LazyEmbedder(loaded.embedding_model, loaded.embedding_dimension),
    )
    answer_pipelines = {
        mode: AnswerPipeline(
            retriever,
            provider,
            token_counter=Utf8ByteUpperBoundCounter(),
            abstention_tau=loaded.answer_abstention_tau,
        )
        for mode, provider in providers.items()
    }
    app = create_app(
        context,
        retriever=retriever,
        answer_pipelines=answer_pipelines,
        shutdown=shutdown,
    )
    app.state.session_factory = sessions
    app.state.llm_providers = MappingProxyType(dict(providers))
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
