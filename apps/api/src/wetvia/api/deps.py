"""Request dependencies. Values come from ``app.state``, never from the environment."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from wetvia.core import LlmProvider
from wetvia.db.engine import DbStatus
from wetvia.retrieval import Retriever


@dataclass(frozen=True, slots=True)
class HealthContext:
    llm_provider: LlmProvider
    version: str
    check_db: Callable[[], Awaitable[DbStatus]]


def get_health_context(request: Request) -> HealthContext:
    context: HealthContext = request.app.state.health_context
    return context


def get_retriever(request: Request) -> Retriever:
    retriever: Retriever | None = getattr(request.app.state, "retriever", None)
    if retriever is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Retrieval is not configured.",
        )
    return retriever
