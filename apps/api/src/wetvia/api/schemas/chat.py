"""Typed request and SSE event DTOs for the server-sent-events chat endpoint."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wetvia.answer.schema import VerifiedAnswer
from wetvia.api.schemas.search import SourceMetadataResponse

type ChatMode = Literal["local", "cloud"]
type ChatRole = Literal["user", "assistant"]


class ChatMessageRequest(BaseModel):
    """A caller-provided user or assistant turn; callers cannot set system prompts."""

    model_config = ConfigDict(extra="forbid")

    role: ChatRole
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message content must not be blank")
        return value


class ChatRequest(BaseModel):
    """One chat turn with bounded preceding conversation history."""

    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessageRequest] = Field(min_length=1, max_length=40)
    peildatum: date | None = None
    mode: ChatMode | None = None

    @model_validator(mode="after")
    def final_message_must_be_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("the final chat message must be from the user")
        if len(self.messages[-1].content) > 2000:
            raise ValueError("the current user message must be at most 2000 characters")
        return self


class ChatSourceCard(BaseModel):
    """A source actually included in the prompt and assigned a visible label."""

    model_config = ConfigDict(extra="forbid")

    label: str
    chunk_id: UUID
    tekst: str
    metadata: SourceMetadataResponse
    score: float


class ChatSourcesEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["sources"]
    sources: list[ChatSourceCard]


class ChatAnswerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["answer"]
    answer: VerifiedAnswer


class ChatErrorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["error"]
    message: str = Field(min_length=1)


class ChatDoneEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["done"]


type ChatEvent = Annotated[
    ChatSourcesEvent | ChatAnswerEvent | ChatErrorEvent | ChatDoneEvent,
    Field(discriminator="type"),
]

__all__ = [
    "ChatAnswerEvent",
    "ChatDoneEvent",
    "ChatErrorEvent",
    "ChatEvent",
    "ChatMessageRequest",
    "ChatMode",
    "ChatRequest",
    "ChatRole",
    "ChatSourceCard",
    "ChatSourcesEvent",
]
