"""FastAPI app factory. Callers pass a ``HealthContext``; this module does not read settings."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from wetvia.api.deps import HealthContext
from wetvia.api.routes import health_router


def create_app(
    context: HealthContext,
    *,
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
    app.include_router(health_router)
    return app
