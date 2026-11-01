"""Request dependencies. Values come from ``app.state``, never from the environment."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from wetvia.answer import AnswerPipeline
from wetvia.api.schemas.chat import ChatMode
from wetvia.db.engine import DbStatus
from wetvia.retrieval import Retriever


@dataclass(frozen=True, slots=True)
class HealthContext:
    version: str
    check_db: Callable[[], Awaitable[DbStatus]]
    local_configured: bool = True
    cloud_configured: bool = False


@dataclass(frozen=True, slots=True)
class ChatContext:
    answer_pipelines: Mapping[ChatMode, AnswerPipeline]


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


def get_chat_context(request: Request) -> ChatContext:
    answer_pipelines: object = getattr(request.app.state, "answer_pipelines", None)
    if not isinstance(answer_pipelines, Mapping) or not answer_pipelines:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is not configured.",
        )
    return ChatContext(answer_pipelines)
