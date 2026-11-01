"""HTTP DTOs for deterministic rule checks."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from wetvia.rules import (
    Dakvlak,
    EisCode,
    Gebiedsbescherming,
    Monumentrelatie,
    Oordeel,
)

CanonicalDecimal = Annotated[
    str,
    StringConstraints(
        strict=True,
        max_length=64,
        pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$",
    ),
]


class DakkapelRuleRequest(BaseModel):
    """Complete input for one Bbl dakkapel check.

    Measurements are canonical, non-negative decimal strings. The browser may
    accept a localized comma, but sends the normalized dot-decimal form here.
    """

    model_config = ConfigDict(extra="forbid")

    dakvlak: Dakvlak
    dakvlak_naar_openbaar_toegankelijk_gebied: StrictBool | None
    plat_dak: StrictBool | None
    hoogte_m: CanonicalDecimal | None
    onderzijde_boven_dakvoet_m: CanonicalDecimal | None
    bovenzijde_onder_daknok_m: CanonicalDecimal | None
    linker_zijkant_tot_dakvlakrand_m: CanonicalDecimal | None
    rechter_zijkant_tot_dakvlakrand_m: CanonicalDecimal | None
    monumentrelatie: Monumentrelatie
    gebiedsbescherming: Gebiedsbescherming


class BronverwijzingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    regeling: str
    artikel: str
    url: str
    bwb_id: str
    toestand_geldig_vanaf: date
    toestand_geldig_tot: date
    toestand_modified: date
    opgehaald_op: date
    bronbestand: str
    bron_url: str
    sha256: str


class EisResultaatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    eis: EisCode
    omschrijving: str
    voldaan: bool | None
    artikel: str
    citaat: str
    contextcitaat: str | None
    toelichting: str | None
    bron: BronverwijzingResponse
    voorbehoud: str
    vergunningcheck_url: str


class ActiviteitResultaatResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activiteit: str
    oordeel: Oordeel
    artikel: str
    citaat: str
    contextcitaat: str
    bron: BronverwijzingResponse
    voorbehoud: str
    vergunningcheck_url: str


class DakkapelRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    eindoordeel: Oordeel
    eisen: list[EisResultaatResponse]
    technische_bouwactiviteit: ActiviteitResultaatResponse
    advies: str | None
    voorbehoud: str
    vergunningcheck_url: str


__all__ = [
    "ActiviteitResultaatResponse",
    "BronverwijzingResponse",
    "DakkapelRuleRequest",
    "DakkapelRuleResponse",
    "EisResultaatResponse",
]
