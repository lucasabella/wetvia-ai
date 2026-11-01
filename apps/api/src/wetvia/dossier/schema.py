"""Versioned data contract for generated dakkapel concept dossiers."""

from datetime import date
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from wetvia.rules import Bronverwijzing, DakkapelInvoer, Toetsresultaat

CONCEPT_DISCLOSURE: Final = (
    "CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een deskundige."
)
CHECKLIST_UNAVAILABLE_NOTE = (
    "De officiële indieningsstukkenlijst van DSO-LV is in deze versie niet opgehaald of "
    "geverifieerd. Daarom bevat dit dossier geen checklistitems. Controleer de stukken "
    "in de officiële Vergunningcheck."
)


class ChecklistStatus(StrEnum):
    """Whether checklist content came from a checked official source."""

    NOT_RETRIEVED = "not_retrieved"
    VERIFIED = "verified"


class AanvragerPlaceholdersV1(BaseModel):
    """Fixed placeholders; generation never accepts applicant personal details."""

    model_config = ConfigDict(extra="forbid")

    naam: str = "[Naam aanvrager invullen]"
    contactgegevens: str = "[Contactgegevens aanvrager invullen]"


class ChecklistItemV1(BaseModel):
    """One document requirement with explicit status and provenance."""

    model_config = ConfigDict(extra="forbid")

    omschrijving: str
    status: ChecklistStatus
    bron: str


class ChecklistV1(BaseModel):
    """Checklist snapshot with explicit source state, including unavailable data."""

    model_config = ConfigDict(extra="forbid")

    bron: str = "DSO-LV"
    status: ChecklistStatus = ChecklistStatus.NOT_RETRIEVED
    toelichting: str = CHECKLIST_UNAVAILABLE_NOTE
    items: list[ChecklistItemV1] = Field(default_factory=list)


class ProjectomschrijvingV1(BaseModel):
    """The sole LLM-generated dossier field."""

    model_config = ConfigDict(extra="forbid")

    projectomschrijving: str = Field(min_length=1, max_length=1800)

    @field_validator("projectomschrijving")
    @classmethod
    def limit_to_120_words(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("projectomschrijving must not be blank")
        if len(cleaned.split()) > 120:
            raise ValueError("projectomschrijving may contain at most 120 words")
        return cleaned


class DossierV1(BaseModel):
    """Complete, versioned concept dossier data rendered to files."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    aanvrager: AanvragerPlaceholdersV1 = Field(default_factory=AanvragerPlaceholdersV1)
    locatie: str = Field(max_length=500)
    projectomschrijving: str = Field(min_length=1, max_length=1800)
    invoer: DakkapelInvoer
    toetsing: Toetsresultaat
    checklist: ChecklistV1 = Field(default_factory=ChecklistV1)
    open_vragen: list[str]
    bronnen: list[Bronverwijzing]
    peildatum: date
    ai_generated: Literal[True] = True
    disclosure: Literal[
        "CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een deskundige."
    ] = CONCEPT_DISCLOSURE


__all__ = [
    "CHECKLIST_UNAVAILABLE_NOTE",
    "CONCEPT_DISCLOSURE",
    "AanvragerPlaceholdersV1",
    "ChecklistItemV1",
    "ChecklistStatus",
    "ChecklistV1",
    "DossierV1",
    "ProjectomschrijvingV1",
]
