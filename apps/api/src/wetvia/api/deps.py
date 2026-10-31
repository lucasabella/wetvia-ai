"""Request dependencies. Values come from ``app.state``, never from the environment."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from wetvia.answer import AnswerPipeline
from wetvia.api.schemas.chat import ChatMode
from wetvia.core import LlmProvider
from wetvia.db.engine import DbStatus
from wetvia.retrieval import Retriever


@dataclass(frozen=True, slots=True)
class HealthContext:
    llm_provider: LlmProvider
    version: str
    check_db: Callable[[], Awaitable[DbStatus]]


@dataclass(frozen=True, slots=True)
class ChatContext:
    answer_pipeline: AnswerPipeline
    configured_mode: ChatMode


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
    answer_pipeline: AnswerPipeline | None = getattr(request.app.state, "answer_pipeline", None)
    configured_mode: object = getattr(request.app.state, "chat_mode", None)
    if answer_pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is not configured.",
        )
    if configured_mode not in {"local", "cloud"}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat mode is not configured.",
        )
    return ChatContext(answer_pipeline, configured_mode)
