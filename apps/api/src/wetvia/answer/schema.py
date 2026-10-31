"""Public structured answer contract."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator

AnswerStatus = Literal["beantwoord", "onzeker", "buiten_scope"]


def _validate_nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("tekst mag niet leeg zijn")
    return value


def _validate_summary(value: str) -> str:
    _validate_nonblank(value)
    if len(value.split()) > 80:
        raise ValueError("samenvatting mag maximaal 80 woorden bevatten")
    return value


class AnswerPoint(BaseModel):
    """One answer claim with the retrieved source chunks that support it."""

    model_config = ConfigDict(extra="forbid")

    tekst: str = Field(min_length=1)
    bron_ids: list[UUID] = Field(min_length=1)

    _nonblank_text = field_validator("tekst")(_validate_nonblank)

    @field_validator("bron_ids")
    @classmethod
    def source_ids_must_be_unique(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("bron_ids moeten uniek zijn")
        return value


class FollowUpStep(BaseModel):
    """A concrete next step with an HTTP(S) destination."""

    model_config = ConfigDict(extra="forbid")

    tekst: str = Field(min_length=1)
    url: AnyHttpUrl

    _nonblank_text = field_validator("tekst")(_validate_nonblank)


class AnswerV1(BaseModel):
    """Version 1 of the answer payload described in docs/02 §4."""

    model_config = ConfigDict(extra="forbid")

    status: AnswerStatus
    samenvatting: str = Field(min_length=1)
    punten: list[AnswerPoint]
    voorbehouden: list[str]
    vervolgstappen: list[FollowUpStep]
    peildatum: date

    _summary_limit = field_validator("samenvatting")(_validate_summary)

    @field_validator("voorbehouden")
    @classmethod
    def caveats_must_be_nonblank(cls, value: list[str]) -> list[str]:
        for caveat in value:
            _validate_nonblank(caveat)
        return value

    @model_validator(mode="after")
    def answered_status_has_cited_points(self) -> "AnswerV1":
        if self.status == "beantwoord" and not self.punten:
            raise ValueError("een beantwoord antwoord moet minstens één bronpunt bevatten")
        return self


class VerifiedAnswer(AnswerV1):
    """Server response; verifier diagnostics are added after model generation."""

    verifier_notes: list[str] = Field(default_factory=list)

    @field_validator("verifier_notes")
    @classmethod
    def verifier_notes_must_be_nonblank(cls, value: list[str]) -> list[str]:
        for note in value:
            _validate_nonblank(note)
        return value


__all__ = ["AnswerPoint", "AnswerStatus", "AnswerV1", "FollowUpStep", "VerifiedAnswer"]
