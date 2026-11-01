"""HTTP DTO for the health check. Not a legal claim."""

from typing import Literal

from pydantic import BaseModel

from wetvia.api.schemas.chat import ChatMode
from wetvia.db.engine import DbStatus


class ConfiguredChatModes(BaseModel):
    """Configured providers; this does not assert that either endpoint responds."""

    local: bool
    cloud: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: DbStatus
    configured_chat_modes: ConfiguredChatModes
    default_chat_mode: ChatMode
    version: str
