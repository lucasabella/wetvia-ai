"""LLM port. Adapters and settings live elsewhere."""

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel
from typing_extensions import TypedDict

ModelT = TypeVar("ModelT", bound=BaseModel)


class ChatMessage(TypedDict):
    role: str
    content: str


@dataclass(frozen=True)
class StreamMetrics:
    """Generation usage reported by providers that expose stream metrics."""

    completion_tokens: int | None
    generation_seconds: float | None


class LLMProvider(Protocol):
    """Chat completion. Streamed schema responses are raw chunks, not prevalidated models."""

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT] | None,
        stream: bool,
        temperature: float,
        *,
        on_metrics: Callable[[StreamMetrics], None] | None = None,
    ) -> ModelT | str | AsyncIterator[str]:
        """Return a model, full text, or raw chunks.

        Callers validate the complete output of a schema-constrained stream.
        """
        ...
