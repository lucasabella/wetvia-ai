"""Request dependencies. Values come from ``app.state``, never from the environment."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request

from wetvia.core import LlmProvider
from wetvia.db.engine import DbStatus


@dataclass(frozen=True, slots=True)
class HealthContext:
    llm_provider: LlmProvider
    version: str
    check_db: Callable[[], Awaitable[DbStatus]]


def get_health_context(request: Request) -> HealthContext:
    context: HealthContext = request.app.state.health_context
    return context
