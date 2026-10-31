"""Tijdelijk AnswerV1 voor de benchmark.

Het schema volgt docs/02 §4. Het echte model hoort later in wetvia.answer.
Dit bestand verzint geen wettekst.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["beantwoord", "onzeker", "buiten_scope"]


class AnswerPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tekst: str
    bron_ids: list[str]


class NextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tekst: str
    url: str


class AnswerV1(BaseModel):
    """Dummy-schema uit docs/02 §4, streng genoeg om schema-validiteit te meten."""

    model_config = ConfigDict(extra="forbid")

    status: Status
    samenvatting: str
    punten: list[AnswerPoint]
    voorbehouden: list[str]
    vervolgstappen: list[NextStep]
    peildatum: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("samenvatting")
    @classmethod
    def samenvatting_max_80_woorden(cls, value: str) -> str:
        """docs/02 §4: max 80 woorden, niet een tekenlimiet."""
        if len(value.split()) > 80:
            msg = "samenvatting mag maximaal 80 woorden zijn"
            raise ValueError(msg)
        return value


def answer_json_schema() -> dict[str, object]:
    schema: dict[str, object] = AnswerV1.model_json_schema()
    return schema


def validate_answer(raw: str) -> bool:
    try:
        AnswerV1.model_validate_json(raw)
    except ValueError:
        return False
    return True
