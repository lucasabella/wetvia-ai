"""HTTP DTO for the health check. Not a legal claim."""

from typing import Literal

from pydantic import BaseModel

from wetvia.core import LlmProvider
from wetvia.db.engine import DbStatus


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: DbStatus
    llm_provider: LlmProvider
    version: str
