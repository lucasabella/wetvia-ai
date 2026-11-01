"""HTTP request model for a generated dakkapel dossier attachment."""

from pydantic import BaseModel, ConfigDict, Field

from wetvia.api.schemas.rules import DakkapelRuleRequest


class DakkapelDossierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    locatie: str | None = Field(default=None, max_length=500)
    invoer: DakkapelRuleRequest


__all__ = ["DakkapelDossierRequest"]
