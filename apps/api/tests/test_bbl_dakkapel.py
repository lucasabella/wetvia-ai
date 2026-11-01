"""Boundary and heritage tests for the pure Bbl dakkapel rule."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from wetvia.rules import (
    VERGUNNINGCHECK_URL,
    VOORBEHOUD_2_29,
    Bbl_2_29_B_2_HOOGTE_MAX_M,
    Bbl_2_29_B_3_ONDERZIJDE_MAX_M,
    Bbl_2_29_B_3_ONDERZIJDE_MIN_M,
    Bbl_2_29_B_4_BOVENZIJDE_MIN_M,
    Bbl_2_29_B_5_ZIJKANT_MIN_M,
    DakkapelInvoer,
    Dakvlak,
    EisCode,
    Gebiedsbescherming,
    Monumentrelatie,
    Oordeel,
    toets,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_Bbl_XML = (
    _REPO_ROOT
    / "packages"
    / "nl-wetten-ingest"
    / "tests"
    / "fixtures"
    / "bwb_xml"
    / "bbl-2026-09-24.xml"
)


def _geldige_invoer(**changes: Any) -> DakkapelInvoer:
    defaults: dict[str, Any] = {
        "dakvlak": Dakvlak.ACHTER,
        "dakvlak_naar_openbaar_toegankelijk_gebied": False,
        "plat_dak": True,
        "hoogte_m": Decimal("1.75"),
        "onderzijde_boven_dakvoet_m": Decimal("0.75"),
        "bovenzijde_onder_daknok_m": Decimal("0.75"),
        "linker_zijkant_tot_dakvlakrand_m": Decimal("0.75"),
        "rechter_zijkant_tot_dakvlakrand_m": Decimal("0.75"),
        "monumentrelatie": Monumentrelatie.GEEN_MONUMENT,
        "gebiedsbescherming": Gebiedsbescherming.GEEN,
    }
    defaults.update(changes)
    return DakkapelInvoer(**defaults)


@pytest.mark.parametrize(
    ("hoogte", "verwacht"),
    [
        (Decimal("0"), True),
        (Decimal("1.75"), True),
        (Decimal("1.750000000000000001"), False),
        (Decimal("2"), False),
        (None, None),
    ],
)
def test_hoogtegrens_is_inclusief_en_exact_decimal(
    hoogte: Decimal | None,
    verwacht: bool | None,
) -> None:
    result = toets(_geldige_invoer(hoogte_m=hoogte))
    assert Bbl_2_29_B_2_HOOGTE_MAX_M == Decimal("1.75")
    assert _eis(result.eisen, EisCode.HOOGTE).voldaan is verwacht


@pytest.mark.parametrize(
    ("onderzijde", "verwacht"),
    [
        (Decimal("0.499999"), False),
        (Decimal("0.5"), False),
        (Decimal("0.5000000001"), True),
        (Decimal("0.9999999999"), True),
        (Decimal("1"), False),
        (Decimal("1.000001"), False),
        (None, None),
    ],
)
def test_onderzijde_heeft_twee_strikte_grenzen(
    onderzijde: Decimal | None,
    verwacht: bool | None,
) -> None:
    result = toets(_geldige_invoer(onderzijde_boven_dakvoet_m=onderzijde))
    assert Bbl_2_29_B_3_ONDERZIJDE_MIN_M == Decimal("0.5")
    assert Bbl_2_29_B_3_ONDERZIJDE_MAX_M == Decimal("1")
    assert _eis(result.eisen, EisCode.ONDERZIJDE).voldaan is verwacht


@pytest.mark.parametrize(
    ("afstand", "verwacht"),
    [
        (Decimal("0.5"), False),
        (Decimal("0.5000000001"), True),
        (Decimal("1.25"), True),
        (None, None),
    ],
)
def test_bovenzijde_afstand_tot_nok_is_strikt(
    afstand: Decimal | None,
    verwacht: bool | None,
) -> None:
    result = toets(_geldige_invoer(bovenzijde_onder_daknok_m=afstand))
    assert Bbl_2_29_B_4_BOVENZIJDE_MIN_M == Decimal("0.5")
    assert _eis(result.eisen, EisCode.BOVENZIJDE).voldaan is verwacht


@pytest.mark.parametrize(
    ("veld", "code"),
    [
        ("linker_zijkant_tot_dakvlakrand_m", EisCode.LINKER_ZIJKANT),
        ("rechter_zijkant_tot_dakvlakrand_m", EisCode.RECHTER_ZIJKANT),
    ],
)
@pytest.mark.parametrize(
    ("afstand", "verwacht"),
    [(Decimal("0.5"), False), (Decimal("0.5000001"), True), (None, None)],
)
def test_beide_zijkanten_worden_afzonderlijk_getoetst(
    veld: str,
    code: EisCode,
    afstand: Decimal | None,
    verwacht: bool | None,
) -> None:
    result = toets(_geldige_invoer(**{veld: afstand}))
    assert Bbl_2_29_B_5_ZIJKANT_MIN_M == Decimal("0.5")
    assert _eis(result.eisen, code).voldaan is verwacht


@pytest.mark.parametrize(
    ("dakvlak", "naar_openbaar", "verwacht"),
    [
        (Dakvlak.ACHTER, None, True),
        (Dakvlak.ACHTER, True, True),
        (Dakvlak.ZIJ, False, True),
        (Dakvlak.ZIJ, True, False),
        (Dakvlak.ZIJ, None, None),
        (Dakvlak.ANDER, False, False),
        (Dakvlak.ONBEKEND, None, None),
    ],
)
def test_locatie_en_openbaar_gebied(
    dakvlak: Dakvlak,
    naar_openbaar: bool | None,
    verwacht: bool | None,
) -> None:
    result = toets(
        _geldige_invoer(
            dakvlak=dakvlak,
            dakvlak_naar_openbaar_toegankelijk_gebied=naar_openbaar,
        )
    )
    assert _eis(result.eisen, EisCode.LOCATIE).voldaan is verwacht


@pytest.mark.parametrize(
    ("relatie", "verwacht", "artikel"),
    [
        (Monumentrelatie.GEEN_MONUMENT, True, "Bbl 2.29, onder b"),
        (Monumentrelatie.IN_AAN_OP, False, "Bbl 2.30, eerste lid"),
        (Monumentrelatie.BIJ, True, "Bbl 2.30, tweede lid, onder b"),
        (Monumentrelatie.ONBEKEND, None, "Bbl 2.30, eerste lid"),
    ],
)
def test_monumentrelatie_houdt_in_aan_op_apart_van_bij(
    relatie: Monumentrelatie,
    verwacht: bool | None,
    artikel: str,
) -> None:
    result = toets(_geldige_invoer(monumentrelatie=relatie))
    monument = _eis(result.eisen, EisCode.MONUMENT)
    assert monument.voldaan is verwacht
    assert monument.artikel == artikel
    if relatie is Monumentrelatie.BIJ:
        assert "onder b" in monument.citaat
        assert monument.contextcitaat is not None and "verricht bij" in monument.contextcitaat
        assert result.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGVRIJ
    if relatie is Monumentrelatie.IN_AAN_OP:
        assert "in, aan of op" in monument.citaat
        assert result.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGPLICHTIG
    if relatie is Monumentrelatie.ONBEKEND:
        assert result.eindoordeel is Oordeel.ONBEPAALD
        assert result.advies is not None and "Vraag na" in result.advies


def test_onbekend_monument_blijft_onbepaald_bij_geometrische_afwijzing() -> None:
    result = toets(
        _geldige_invoer(
            monumentrelatie=Monumentrelatie.ONBEKEND,
            hoogte_m=Decimal("1.8"),
        )
    )

    assert _eis(result.eisen, EisCode.HOOGTE).voldaan is False
    assert _eis(result.eisen, EisCode.MONUMENT).voldaan is None
    assert result.eindoordeel is Oordeel.ONBEPAALD
    assert result.advies is not None and "Vraag na" in result.advies


def test_bekend_monument_in_aan_op_beslist_bij_geometrische_afwijzing() -> None:
    result = toets(
        _geldige_invoer(
            monumentrelatie=Monumentrelatie.IN_AAN_OP,
            hoogte_m=Decimal("1.8"),
        )
    )

    assert _eis(result.eisen, EisCode.HOOGTE).voldaan is False
    assert _eis(result.eisen, EisCode.MONUMENT).voldaan is False
    assert result.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGPLICHTIG


@pytest.mark.parametrize(
    ("gebied", "dakvlak", "naar_openbaar", "verwacht"),
    [
        (Gebiedsbescherming.GEEN, Dakvlak.ACHTER, False, True),
        (
            Gebiedsbescherming.RIJKSBESCHERMD_STADS_OF_DORPSGEZICHT,
            Dakvlak.ACHTER,
            False,
            True,
        ),
        (
            Gebiedsbescherming.RIJKSBESCHERMD_STADS_OF_DORPSGEZICHT,
            Dakvlak.ACHTER,
            True,
            False,
        ),
        (
            Gebiedsbescherming.RIJKSBESCHERMD_STADS_OF_DORPSGEZICHT,
            Dakvlak.ZIJ,
            False,
            False,
        ),
        (
            Gebiedsbescherming.RIJKSBESCHERMD_STADS_OF_DORPSGEZICHT,
            Dakvlak.ONBEKEND,
            None,
            None,
        ),
        (Gebiedsbescherming.ONBEKEND, Dakvlak.ACHTER, False, None),
    ],
)
def test_rijksbeschermd_stads_of_dorpsgezicht(
    gebied: Gebiedsbescherming,
    dakvlak: Dakvlak,
    naar_openbaar: bool | None,
    verwacht: bool | None,
) -> None:
    result = toets(
        _geldige_invoer(
            gebiedsbescherming=gebied,
            dakvlak=dakvlak,
            dakvlak_naar_openbaar_toegankelijk_gebied=naar_openbaar,
        )
    )
    assert _eis(result.eisen, EisCode.GEBIEDSBESCHERMING).voldaan is verwacht


def test_onbekend_beschermd_gebied_geeft_niet_onbepaald_bij_andere_zekere_afwijzing() -> None:
    result = toets(
        _geldige_invoer(
            gebiedsbescherming=Gebiedsbescherming.ONBEKEND,
            hoogte_m=Decimal("1.8"),
        )
    )

    assert _eis(result.eisen, EisCode.GEBIEDSBESCHERMING).voldaan is None
    assert _eis(result.eisen, EisCode.HOOGTE).voldaan is False
    assert result.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGPLICHTIG


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_negatieve_of_niet_eindige_maten_zijn_ongeldig(value: Decimal) -> None:
    with pytest.raises(ValueError):
        _geldige_invoer(hoogte_m=value)


@pytest.mark.parametrize("value", [0.5, 1, "0.5", True])
def test_maten_accepteren_alleen_decimal_of_none(value: object) -> None:
    with pytest.raises(TypeError, match="Decimal"):
        _geldige_invoer(hoogte_m=value)


@pytest.mark.parametrize("field", ["plat_dak", "dakvlak_naar_openbaar_toegankelijk_gebied"])
def test_booleanvelden_accepteren_geen_getallen(field: str) -> None:
    with pytest.raises(TypeError, match="bool of None"):
        _geldige_invoer(**{field: 1})


def test_enums_and_toets_validate_invalid_input_types() -> None:
    with pytest.raises(TypeError, match="dakvlak moet een Dakvlak"):
        _geldige_invoer(dakvlak="achterdakvlak")
    with pytest.raises(TypeError, match="invoer moet een DakkapelInvoer"):
        toets("not an input")  # type: ignore[arg-type]


def test_resultaat_separates_technical_building_activity() -> None:
    result = toets(_geldige_invoer(hoogte_m=Decimal("1.8")))

    assert result.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGPLICHTIG
    assert result.technische_bouwactiviteit.oordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGVRIJ
    assert result.technische_bouwactiviteit.artikel == "Bbl 2.27, tweede lid, onder a"
    assert result.technische_bouwactiviteit.citaat == "een dakkapel;"
    assert "artikel 5.1, tweede lid" in result.technische_bouwactiviteit.contextcitaat


def test_every_result_has_the_severe_disfigurement_caveat_and_vergunningcheck_link() -> None:
    result = toets(_geldige_invoer())

    assert result.voorbehoud == VOORBEHOUD_2_29
    assert result.vergunningcheck_url == VERGUNNINGCHECK_URL
    all_results = (*result.eisen, result.technische_bouwactiviteit)
    assert len(result.eisen) == len(EisCode)
    assert all(item.voorbehoud == VOORBEHOUD_2_29 for item in all_results)
    assert all(item.vergunningcheck_url == VERGUNNINGCHECK_URL for item in all_results)


def test_quotes_and_source_provenance_match_the_saved_official_bbl_xml() -> None:
    result = toets(_geldige_invoer(monumentrelatie=Monumentrelatie.BIJ))
    article_text = {article: _article_text(article) for article in ("2.27", "2.29", "2.30")}

    for item in result.eisen:
        article = item.bron.artikel.removeprefix("Bbl ")
        assert " ".join(item.citaat.split()) in article_text[article]
        if item.contextcitaat is not None:
            assert " ".join(item.contextcitaat.split()) in article_text[article]
        assert item.bron.bwb_id == "BWBR0041297"
        assert item.bron.toestand_geldig_vanaf == date(2026, 9, 24)
        assert item.bron.toestand_geldig_tot == date(9999, 12, 31)
        assert item.bron.toestand_modified == date(2026, 9, 30)
        assert item.bron.opgehaald_op == date(2026, 10, 31)
        assert item.bron.url.endswith(f"artikel={article}&z=2026-09-24&g=2026-09-24")
        assert item.bron.bronbestand.endswith("bbl-2026-09-24.xml")
    technical = result.technische_bouwactiviteit
    assert technical.citaat in article_text["2.27"]
    assert " ".join(technical.contextcitaat.split()) in article_text["2.27"]
    assert VOORBEHOUD_2_29 in article_text["2.29"]
    assert hashlib.sha256(_Bbl_XML.read_bytes()).hexdigest() == result.eisen[0].bron.sha256


def test_constants_retain_exact_decimal_thresholds() -> None:
    assert Bbl_2_29_B_2_HOOGTE_MAX_M == Decimal("1.75")
    assert Bbl_2_29_B_3_ONDERZIJDE_MIN_M == Decimal("0.5")
    assert Bbl_2_29_B_3_ONDERZIJDE_MAX_M == Decimal("1")
    assert Bbl_2_29_B_4_BOVENZIJDE_MIN_M == Decimal("0.5")
    assert Bbl_2_29_B_5_ZIJKANT_MIN_M == Decimal("0.5")


@lru_cache(maxsize=1)
def _article_text(article: str) -> str:
    section = "2.3.2" if article == "2.27" else "2.3.3"
    path = f"/Hoofdstuk2/Afdeling2.3/Paragraaf{section}/Artikel{article}"
    root = ET.parse(_Bbl_XML).getroot()
    element = root.find(f".//artikel[@bwb-ng-variabel-deel='{path}']")
    assert element is not None
    return " ".join("".join(element.itertext()).split())


def _eis(eisen: tuple[Any, ...], code: EisCode) -> Any:
    return next(eis for eis in eisen if eis.eis is code)
