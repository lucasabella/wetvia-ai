"""SSE chat route. The answer pipeline and configured mode come from app state."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from wetvia.answer import IncludedAnswerSource
from wetvia.api.deps import ChatContext, get_chat_context
from wetvia.api.schemas.chat import (
    ChatAnswerEvent,
    ChatDoneEvent,
    ChatErrorEvent,
    ChatEvent,
    ChatRequest,
    ChatSourceCard,
    ChatSourcesEvent,
)
from wetvia.api.schemas.search import SourceMetadataResponse
from wetvia.llm import ChatMessage

_SAFE_ERROR_MESSAGE = "Er is een fout opgetreden bij het opstellen van het antwoord."
_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}

router = APIRouter(prefix="/api", tags=["chat"])


@router.post(
    "/chat",
    response_model=None,
    response_class=StreamingResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "Server-sent events: sources, answer, optional error, then done.",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "x-event-schema": {"$ref": "#/components/schemas/ChatEvent"},
                }
            },
        }
    },
)
async def chat(
    request: ChatRequest,
    context: Annotated[ChatContext, Depends(get_chat_context)],
) -> StreamingResponse:
    """Generate one answer; never switch providers based on request input."""
    if request.mode is not None and request.mode != context.configured_mode:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Requested chat mode is unavailable.",
        )

    current_message = request.messages[-1]
    history = tuple(
        ChatMessage(role=message.role, content=message.content) for message in request.messages[:-1]
    )
    peildatum = request.peildatum or date.today()

    async def event_stream() -> AsyncIterator[bytes]:
        queue: asyncio.Queue[tuple[ChatEvent, asyncio.Future[None] | None]] = asyncio.Queue(
            maxsize=2
        )

        async def emit_sources(sources: Sequence[IncludedAnswerSource]) -> None:
            cards = [
                ChatSourceCard(
                    label=included.label,
                    chunk_id=included.source.chunk_id,
                    tekst=included.source.tekst,
                    metadata=SourceMetadataResponse.model_validate(
                        included.source.metadata,
                        from_attributes=True,
                    ),
                    score=included.score,
                )
                for included in sources
            ]
            acknowledged = asyncio.get_running_loop().create_future()
            await queue.put((ChatSourcesEvent(type="sources", sources=cards), acknowledged))
            await acknowledged

        async def generate_answer() -> None:
            try:
                result = await context.answer_pipeline.answer(
                    current_message.content,
                    peildatum,
                    history=history,
                    on_sources=emit_sources,
                )
                await queue.put((ChatAnswerEvent(type="answer", answer=result), None))
            except asyncio.CancelledError:
                raise
            except Exception:
                await queue.put((ChatErrorEvent(type="error", message=_SAFE_ERROR_MESSAGE), None))
            await queue.put((ChatDoneEvent(type="done"), None))

        task = asyncio.create_task(generate_answer())
        try:
            while True:
                event, acknowledged = await queue.get()
                yield _encode_event(event)
                if acknowledged is not None and not acknowledged.done():
                    acknowledged.set_result(None)
                if isinstance(event, ChatDoneEvent):
                    break
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_NO_CACHE_HEADERS,
    )


def _encode_event(event: ChatEvent) -> bytes:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.type}\ndata: {data}\n\n".encode()


__all__ = ["router"]
