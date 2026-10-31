"""In-memory provider for tests. No network."""

from collections.abc import AsyncIterator, Sequence

from wetvia.llm.parsing import parse_with_one_retry
from wetvia.llm.ports import ChatMessage, ModelT


class FakeProvider:
    """Replay scripted text. Schema calls use the same one-retry validation as the HTTP adapters."""

    def __init__(self, replies: Sequence[str], chunks: Sequence[str] = ()) -> None:
        self._replies = list(replies)
        self._chunks = list(chunks)
        self.calls: list[tuple[Sequence[ChatMessage], type[object] | None, bool, float]] = []

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT] | None,
        stream: bool,
        temperature: float,
    ) -> ModelT | str | AsyncIterator[str]:
        self.calls.append((messages, schema, stream, temperature))
        if schema is not None:
            if stream:
                raise ValueError("schema and stream cannot be combined")
            return await parse_with_one_retry(schema, messages, self._next_reply)
        if stream:
            return self._iterate_chunks()
        return self._next_reply_sync()

    def _next_reply_sync(self) -> str:
        if not self._replies:
            raise RuntimeError("FakeProvider has no replies left")
        return self._replies.pop(0)

    async def _next_reply(self, _messages: Sequence[ChatMessage]) -> str:
        return self._next_reply_sync()

    async def _iterate_chunks(self) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk
