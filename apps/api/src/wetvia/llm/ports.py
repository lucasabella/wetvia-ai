"""LLM port. Adapters and settings live elsewhere."""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel
from typing_extensions import TypedDict

ModelT = TypeVar("ModelT", bound=BaseModel)


class ChatMessage(TypedDict):
    role: str
    content: str


class LLMProvider(Protocol):
    """Chat completion. ``stream`` yields text only when ``schema`` is None."""

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT] | None,
        stream: bool,
        temperature: float,
    ) -> ModelT | str | AsyncIterator[str]:
        """Return a validated model, the full text, or an async iterator of text chunks."""
        ...
