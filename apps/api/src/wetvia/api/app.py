"""FastAPI app factory. Callers pass a ``HealthContext``; this module does not read settings."""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from types import MappingProxyType
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import TypeAdapter

from wetvia.answer import AnswerPipeline
from wetvia.api.deps import HealthContext
from wetvia.api.routes import chat_router, health_router, search_router
from wetvia.api.schemas.chat import (
    ChatAnswerEvent,
    ChatDoneEvent,
    ChatErrorEvent,
    ChatEvent,
    ChatMode,
    ChatSourcesEvent,
)
from wetvia.retrieval import Retriever


def create_app(
    context: HealthContext,
    *,
    retriever: Retriever | None = None,
    answer_pipelines: Mapping[ChatMode, AnswerPipeline] | None = None,
    shutdown: Callable[[], Awaitable[None]] | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if shutdown is not None:
            await shutdown()

    app = FastAPI(
        title="Wetvia",
        version=context.version,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.health_context = context
    app.state.retriever = retriever
    app.state.answer_pipelines = MappingProxyType(dict(answer_pipelines or {}))
    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(chat_router)

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        components: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in (ChatSourcesEvent, ChatAnswerEvent, ChatErrorEvent, ChatDoneEvent):
            model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            definitions = model_schema.pop("$defs", {})
            for name, definition in definitions.items():
                components.setdefault(name, definition)
            components[model.__name__] = model_schema
        event_schema = TypeAdapter(ChatEvent).json_schema(
            ref_template="#/components/schemas/{model}"
        )
        for name, definition in event_schema.pop("$defs", {}).items():
            components.setdefault(name, definition)
        components["ChatEvent"] = event_schema
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app
