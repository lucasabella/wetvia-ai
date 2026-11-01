"""Pure, deterministic checks for a dakkapel under the saved Bbl text."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum, StrEnum

Bbl_2_29_B_2_HOOGTE_MAX_M = Decimal("1.75")
Bbl_2_29_B_3_ONDERZIJDE_MIN_M = Decimal("0.5")
Bbl_2_29_B_3_ONDERZIJDE_MAX_M = Decimal("1")
Bbl_2_29_B_4_BOVENZIJDE_MIN_M = Decimal("0.5")
Bbl_2_29_B_5_ZIJKANT_MIN_M = Decimal("0.5")

VERGUNNINGCHECK_URL = "https://omgevingswet.overheid.nl/checken"
VOORBEHOUD_2_29 = (
    "Onverminderd regels in het omgevingsplan over het in stand houden van een "
    "bouwwerk die betrekking hebben op de ernstige ontsiering van het uiterlijk "
    "van dat bouwwerk,"
)

_BWB_ID = "BWBR0041297"
_TOESTAND_START = date(2026, 9, 24)
_TOESTAND_EINDE = date(9999, 12, 31)
_TOESTAND_MODIFIED = date(2026, 9, 30)
_BRON_OPGEHAALD_OP = date(2026, 10, 31)
_BRON_BESTAND = "packages/nl-wetten-ingest/tests/fixtures/bwb_xml/bbl-2026-09-24.xml"
_BRON_URL = (
    "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/"
    "2026-09-24_0/xml/BWBR0041297_2026-09-24_0.xml"
)
_BRON_SHA256 = "52ef1dbbf8d109ba9c1e452193735ef32790d604dec0c8e03ede02245c6b7690"
_ARTIKEL_URLS = {
    "2.27": "https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.27&z=2026-09-24&g=2026-09-24",
    "2.29": "https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.29&z=2026-09-24&g=2026-09-24",
    "2.30": "https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.30&z=2026-09-24&g=2026-09-24",
}

_CITAAT_2_27_LID2_A = "een dakkapel;"
_CITAAT_2_27_LID2_AANHEF = (
    "In afwijking van de artikelen 2.25 en 2.26 en ongeacht of een uitzondering als bedoeld "
    "in het eerste lid van toepassing is, geldt het verbod, bedoeld in artikel 5.1, tweede lid, "
    "van de wet, om zonder omgevingsvergunning een bouwactiviteit te verrichten ook niet voor "
    "een bouwactiviteit die betrekking heeft op een van de volgende bouwwerken:"
)
_CITAAT_2_29_B = (
    "een dakkapel in het achterdakvlak of een niet naar openbaar toegankelijk "
    "gebied gekeerd zijdakvlak, als wordt voldaan aan de volgende eisen:"
)
_CITAAT_2_29_B_1 = "voorzien van een plat dak;"
_CITAAT_2_29_B_2 = "gemeten vanaf de voet van de dakkapel niet hoger dan 1,75 m;"
_CITAAT_2_29_B_3 = "onderzijde meer dan 0,5 m en minder dan 1 m boven de dakvoet;"
_CITAAT_2_29_B_4 = "bovenzijde meer dan 0,5 m onder de daknok; en"
_CITAAT_2_29_B_5 = "zijkanten meer dan 0,5 m van de zijkanten van het dakvlak;"
_CITAAT_2_30_LID1 = (
    "Op een omgevingsplanactiviteit die wordt verricht in, aan of op een "
    "gemeentelijk monument, voorbeschermd gemeentelijk monument, provinciaal "
    "monument, voorbeschermd provinciaal monument, rijksmonument of "
    "voorbeschermd rijksmonument is alleen artikel 2.29, onder a, van toepassing."
)
_CITAAT_2_30_LID2_AANHEF = (
    "Op een omgevingsplanactiviteit die wordt verricht bij een gemeentelijk monument, "
    "voorbeschermd gemeentelijk monument, provinciaal monument, voorbeschermd provinciaal "
    "monument, rijksmonument of voorbeschermd rijksmonument zijn alleen de volgende "
    "onderdelen van artikel 2.29 van toepassing:"
)
_CITAAT_2_30_LID2_B = "artikel 2.29, onder b, c, f, h, i, k, l, p, onder 2° tot en met 8°, q en r."
_CITAAT_2_30_LID3_B_2 = (
    "een wijziging van een achtergevel of achterdakvlak, als die gevel of dat "
    "dakvlak niet naar openbaar toegankelijk gebied is gekeerd;"
)


class Dakvlak(StrEnum):
    """Roof face where the dakkapel is placed."""

    ACHTER = "achterdakvlak"
    ZIJ = "zijdakvlak"
    ANDER = "ander_dakvlak"
    ONBEKEND = "onbekend"


class Monumentrelatie(StrEnum):
    """Relation of the work to any protected monument type named in Bbl 2.30."""

    GEEN_MONUMENT = "geen_monument"
    IN_AAN_OP = "in_aan_of_op_monument"
    BIJ = "bij_monument"
    ONBEKEND = "onbekend"


class Gebiedsbescherming(StrEnum):
    GEEN = "geen_rijksbeschermd_stads_of_dorpsgezicht"
    RIJKSBESCHERMD_STADS_OF_DORPSGEZICHT = "rijksbeschermd_stads_of_dorpsgezicht"
    ONBEKEND = "onbekend"


class Oordeel(StrEnum):
    WAARSCHIJNLIJK_VERGUNNINGVRIJ = "waarschijnlijk_vergunningvrij"
    WAARSCHIJNLIJK_VERGUNNINGPLICHTIG = "waarschijnlijk_vergunningplichtig"
    ONBEPAALD = "onbepaald"


class EisCode(StrEnum):
    LOCATIE = "locatie"
    PLAT_DAK = "plat_dak"
    HOOGTE = "hoogte"
    ONDERZIJDE = "onderzijde"
    BOVENZIJDE = "bovenzijde"
    LINKER_ZIJKANT = "linker_zijkant"
    RECHTER_ZIJKANT = "rechter_zijkant"
    MONUMENT = "monument"
    GEBIEDSBESCHERMING = "gebiedsbescherming"


@dataclass(frozen=True, slots=True)
class DakkapelInvoer:
    """Facts needed for the Bbl dakkapel check; ``None`` means not known."""

    dakvlak: Dakvlak = Dakvlak.ONBEKEND
    dakvlak_naar_openbaar_toegankelijk_gebied: bool | None = None
    plat_dak: bool | None = None
    hoogte_m: Decimal | None = None
    onderzijde_boven_dakvoet_m: Decimal | None = None
    bovenzijde_onder_daknok_m: Decimal | None = None
    linker_zijkant_tot_dakvlakrand_m: Decimal | None = None
    rechter_zijkant_tot_dakvlakrand_m: Decimal | None = None
    monumentrelatie: Monumentrelatie = Monumentrelatie.ONBEKEND
    gebiedsbescherming: Gebiedsbescherming = Gebiedsbescherming.ONBEKEND

    def __post_init__(self) -> None:
        _require_enum("dakvlak", self.dakvlak, Dakvlak)
        _require_enum("monumentrelatie", self.monumentrelatie, Monumentrelatie)
        _require_enum("gebiedsbescherming", self.gebiedsbescherming, Gebiedsbescherming)
        _require_optional_bool(
            "dakvlak_naar_openbaar_toegankelijk_gebied",
            self.dakvlak_naar_openbaar_toegankelijk_gebied,
        )
        _require_optional_bool("plat_dak", self.plat_dak)
        for name in (
            "hoogte_m",
            "onderzijde_boven_dakvoet_m",
            "bovenzijde_onder_daknok_m",
            "linker_zijkant_tot_dakvlakrand_m",
            "rechter_zijkant_tot_dakvlakrand_m",
        ):
            _require_optional_measurement(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class Bronverwijzing:
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


@dataclass(frozen=True, slots=True)
class EisResultaat:
    eis: EisCode
    omschrijving: str
    voldaan: bool | None
    artikel: str
    citaat: str
    contextcitaat: str | None
    toelichting: str | None
    bron: Bronverwijzing
    voorbehoud: str
    vergunningcheck_url: str


@dataclass(frozen=True, slots=True)
class ActiviteitResultaat:
    activiteit: str
    oordeel: Oordeel
    artikel: str
    citaat: str
    contextcitaat: str
    bron: Bronverwijzing
    voorbehoud: str
    vergunningcheck_url: str


@dataclass(frozen=True, slots=True)
class Toetsresultaat:
    eindoordeel: Oordeel
    eisen: tuple[EisResultaat, ...]
    technische_bouwactiviteit: ActiviteitResultaat
    advies: str | None
    voorbehoud: str
    vergunningcheck_url: str


def toets(invoer: DakkapelInvoer) -> Toetsresultaat:
    """Check each relevant requirement independently using exact Decimal limits.

    The overall judgment is about the Bbl omgevingsplanactiviteit exemption in
    article 2.29(b). The technical building activity in article 2.27(2)(a) is
    reported separately and does not change that judgment.
    """
    if not isinstance(invoer, DakkapelInvoer):
        raise TypeError("invoer moet een DakkapelInvoer zijn")

    eisen = (
        _maak_eis(
            EisCode.LOCATIE,
            "De dakkapel ligt in het achterdakvlak of in een niet-openbaar zijdakvlak.",
            _locatie_voldoet(invoer),
            "Bbl 2.29, onder b",
            _CITAAT_2_29_B,
            _locatie_toelichting(invoer),
            "2.29",
        ),
        _maak_eis(
            EisCode.PLAT_DAK,
            "De dakkapel heeft een plat dak.",
            invoer.plat_dak,
            "Bbl 2.29, onder b, onder 1°",
            _CITAAT_2_29_B_1,
            None if invoer.plat_dak is not None else "Vul in of het dak plat is.",
            "2.29",
        ),
        _maak_eis(
            EisCode.HOOGTE,
            "De hoogte vanaf de voet is niet groter dan 1,75 m.",
            _meetwaarde_voldoet(
                invoer.hoogte_m,
                lambda value: value <= Bbl_2_29_B_2_HOOGTE_MAX_M,
            ),
            "Bbl 2.29, onder b, onder 2°",
            _CITAAT_2_29_B_2,
            _meetwaarde_toelichting(
                invoer.hoogte_m,
                f"Meet de hoogte vanaf de voet van de dakkapel; grens is "
                f"{Bbl_2_29_B_2_HOOGTE_MAX_M} m.",
            ),
            "2.29",
        ),
        _maak_eis(
            EisCode.ONDERZIJDE,
            "De onderzijde ligt meer dan 0,5 m en minder dan 1 m boven de dakvoet.",
            _meetwaarde_voldoet(
                invoer.onderzijde_boven_dakvoet_m,
                lambda value: Bbl_2_29_B_3_ONDERZIJDE_MIN_M < value < Bbl_2_29_B_3_ONDERZIJDE_MAX_M,
            ),
            "Bbl 2.29, onder b, onder 3°",
            _CITAAT_2_29_B_3,
            _meetwaarde_toelichting(
                invoer.onderzijde_boven_dakvoet_m,
                "Meet de onderzijde boven de dakvoet; beide grenzen zijn strikt.",
            ),
            "2.29",
        ),
        _maak_eis(
            EisCode.BOVENZIJDE,
            "De bovenzijde ligt meer dan 0,5 m onder de daknok.",
            _meetwaarde_voldoet(
                invoer.bovenzijde_onder_daknok_m,
                lambda value: value > Bbl_2_29_B_4_BOVENZIJDE_MIN_M,
            ),
            "Bbl 2.29, onder b, onder 4°",
            _CITAAT_2_29_B_4,
            _meetwaarde_toelichting(
                invoer.bovenzijde_onder_daknok_m,
                "Meet de vrije afstand tussen de bovenzijde en de daknok; de grens is strikt.",
            ),
            "2.29",
        ),
        _maak_eis(
            EisCode.LINKER_ZIJKANT,
            "De linkerzijkant ligt meer dan 0,5 m van de rand van het dakvlak.",
            _meetwaarde_voldoet(
                invoer.linker_zijkant_tot_dakvlakrand_m,
                lambda value: value > Bbl_2_29_B_5_ZIJKANT_MIN_M,
            ),
            "Bbl 2.29, onder b, onder 5°",
            _CITAAT_2_29_B_5,
            _meetwaarde_toelichting(
                invoer.linker_zijkant_tot_dakvlakrand_m,
                "Meet de afstand van de linkerzijkant tot de zijkant van het dakvlak; "
                "de grens is strikt.",
            ),
            "2.29",
        ),
        _maak_eis(
            EisCode.RECHTER_ZIJKANT,
            "De rechterzijkant ligt meer dan 0,5 m van de rand van het dakvlak.",
            _meetwaarde_voldoet(
                invoer.rechter_zijkant_tot_dakvlakrand_m,
                lambda value: value > Bbl_2_29_B_5_ZIJKANT_MIN_M,
            ),
            "Bbl 2.29, onder b, onder 5°",
            _CITAAT_2_29_B_5,
            _meetwaarde_toelichting(
                invoer.rechter_zijkant_tot_dakvlakrand_m,
                "Meet de afstand van de rechterzijkant tot de zijkant van het dakvlak; "
                "de grens is strikt.",
            ),
            "2.29",
        ),
        _monument_eis(invoer.monumentrelatie),
        _gebiedseis(invoer),
    )

    if any(eis.voldaan is False for eis in eisen):
        eindoordeel = Oordeel.WAARSCHIJNLIJK_VERGUNNINGPLICHTIG
    elif any(eis.voldaan is None for eis in eisen):
        eindoordeel = Oordeel.ONBEPAALD
    else:
        eindoordeel = Oordeel.WAARSCHIJNLIJK_VERGUNNINGVRIJ

    return Toetsresultaat(
        eindoordeel=eindoordeel,
        eisen=eisen,
        technische_bouwactiviteit=_technische_bouwactiviteit(),
        advies=_advies(invoer, eisen),
        voorbehoud=VOORBEHOUD_2_29,
        vergunningcheck_url=VERGUNNINGCHECK_URL,
    )


def _locatie_voldoet(invoer: DakkapelInvoer) -> bool | None:
    if invoer.dakvlak is Dakvlak.ACHTER:
        return True
    if invoer.dakvlak is Dakvlak.ZIJ:
        openbaar = invoer.dakvlak_naar_openbaar_toegankelijk_gebied
        return None if openbaar is None else not openbaar
    if invoer.dakvlak is Dakvlak.ANDER:
        return False
    return None


def _locatie_toelichting(invoer: DakkapelInvoer) -> str | None:
    if invoer.dakvlak is Dakvlak.ZIJ:
        if invoer.dakvlak_naar_openbaar_toegankelijk_gebied is None:
            return "Geef aan of het zijdakvlak naar openbaar toegankelijk gebied is gekeerd."
        if invoer.dakvlak_naar_openbaar_toegankelijk_gebied:
            return "Dit zijdakvlak is naar openbaar toegankelijk gebied gekeerd."
    elif invoer.dakvlak is Dakvlak.ONBEKEND:
        return "Geef aan of de dakkapel in het achterdakvlak of een zijdakvlak komt."
    return None


def _monument_eis(relatie: Monumentrelatie) -> EisResultaat:
    contextcitaat: str | None = None
    bronartikel = "2.30"
    if relatie is Monumentrelatie.IN_AAN_OP:
        voldaan: bool | None = False
        artikel = "Bbl 2.30, eerste lid"
        citaat = _CITAAT_2_30_LID1
        toelichting = "Voor deze activiteit op, aan of in het monument geldt 2.29 onder b niet."
    elif relatie is Monumentrelatie.BIJ:
        voldaan = True
        artikel = "Bbl 2.30, tweede lid, onder b"
        citaat = _CITAAT_2_30_LID2_B
        contextcitaat = _CITAAT_2_30_LID2_AANHEF
        toelichting = (
            "De invoer zegt dat de activiteit bij het monument is. Artikel 2.30, tweede lid, "
            "noemt artikel 2.29, onder b; alleen 'bij' maakt deze dakkapeltoets dus niet negatief."
        )
    elif relatie is Monumentrelatie.GEEN_MONUMENT:
        voldaan = True
        artikel = "Bbl 2.29, onder b"
        citaat = _CITAAT_2_29_B
        contextcitaat = None
        bronartikel = "2.29"
        toelichting = "Volgens de invoer is de activiteit niet in, aan of op een monument."
    else:
        voldaan = None
        artikel = "Bbl 2.30, eerste lid"
        citaat = _CITAAT_2_30_LID1
        contextcitaat = None
        toelichting = (
            "Vraag na of de activiteit in, aan of op een beschermd monument wordt verricht."
        )
    return _maak_eis(
        EisCode.MONUMENT,
        "De monumentregels beperken de toepassing van artikel 2.29, onder b, niet.",
        voldaan,
        artikel,
        citaat,
        toelichting,
        bronartikel,
        contextcitaat=contextcitaat,
    )


def _gebiedseis(invoer: DakkapelInvoer) -> EisResultaat:
    if invoer.gebiedsbescherming is Gebiedsbescherming.GEEN:
        voldaan: bool | None = True
        toelichting = (
            "Volgens de invoer ligt de locatie niet in een rijksbeschermd stads- of dorpsgezicht."
        )
    elif invoer.gebiedsbescherming is Gebiedsbescherming.ONBEKEND:
        voldaan = None
        toelichting = (
            "Controleer of de locatie de functie-aanduiding rijksbeschermd "
            "stads- of dorpsgezicht heeft."
        )
    elif invoer.dakvlak is Dakvlak.ONBEKEND:
        voldaan = None
        toelichting = "Geef aan of de dakkapel in het achterdakvlak komt."
    elif invoer.dakvlak is not Dakvlak.ACHTER:
        voldaan = False
        toelichting = "In dit beschermde gezicht geldt de uitzondering voor een achterdakvlak."
    elif invoer.dakvlak_naar_openbaar_toegankelijk_gebied is None:
        voldaan = None
        toelichting = "Geef aan of het achterdakvlak naar openbaar toegankelijk gebied is gekeerd."
    elif invoer.dakvlak_naar_openbaar_toegankelijk_gebied:
        voldaan = False
        toelichting = "Het achterdakvlak is naar openbaar toegankelijk gebied gekeerd."
    else:
        voldaan = True
        toelichting = None
    return _maak_eis(
        EisCode.GEBIEDSBESCHERMING,
        "In een rijksbeschermd stads- of dorpsgezicht moet het achterdakvlak niet "
        "naar openbaar gebied zijn gekeerd.",
        voldaan,
        "Bbl 2.30, derde lid, onder b, onder 2°",
        _CITAAT_2_30_LID3_B_2,
        toelichting,
        "2.30",
    )


def _technische_bouwactiviteit() -> ActiviteitResultaat:
    return ActiviteitResultaat(
        activiteit="bouwactiviteit (technisch)",
        oordeel=Oordeel.WAARSCHIJNLIJK_VERGUNNINGVRIJ,
        artikel="Bbl 2.27, tweede lid, onder a",
        citaat=_CITAAT_2_27_LID2_A,
        contextcitaat=_CITAAT_2_27_LID2_AANHEF,
        bron=_bronverwijzing("2.27"),
        voorbehoud=VOORBEHOUD_2_29,
        vergunningcheck_url=VERGUNNINGCHECK_URL,
    )


def _maak_eis(
    eis: EisCode,
    omschrijving: str,
    voldaan: bool | None,
    artikel: str,
    citaat: str,
    toelichting: str | None,
    bronartikel: str,
    *,
    contextcitaat: str | None = None,
) -> EisResultaat:
    return EisResultaat(
        eis=eis,
        omschrijving=omschrijving,
        voldaan=voldaan,
        artikel=artikel,
        citaat=citaat,
        contextcitaat=contextcitaat,
        toelichting=toelichting,
        bron=_bronverwijzing(bronartikel),
        voorbehoud=VOORBEHOUD_2_29,
        vergunningcheck_url=VERGUNNINGCHECK_URL,
    )


def _bronverwijzing(artikel: str) -> Bronverwijzing:
    return Bronverwijzing(
        regeling="Besluit bouwwerken leefomgeving (Bbl)",
        artikel=f"Bbl {artikel}",
        url=_ARTIKEL_URLS[artikel],
        bwb_id=_BWB_ID,
        toestand_geldig_vanaf=_TOESTAND_START,
        toestand_geldig_tot=_TOESTAND_EINDE,
        toestand_modified=_TOESTAND_MODIFIED,
        opgehaald_op=_BRON_OPGEHAALD_OP,
        bronbestand=_BRON_BESTAND,
        bron_url=_BRON_URL,
        sha256=_BRON_SHA256,
    )


def _meetwaarde_voldoet(
    value: Decimal | None,
    check: Callable[[Decimal], bool],
) -> bool | None:
    if value is None:
        return None
    return check(value)


def _meetwaarde_toelichting(value: Decimal | None, unknown: str) -> str | None:
    return unknown if value is None else None


def _advies(invoer: DakkapelInvoer, eisen: tuple[EisResultaat, ...]) -> str | None:
    adviezen: list[str] = []
    monument = next(eis for eis in eisen if eis.eis is EisCode.MONUMENT)
    if monument.voldaan is None:
        adviezen.append(
            "Vraag na of de dakkapel in, aan of op het monument komt, of alleen bij het monument."
        )
    gebied = next(eis for eis in eisen if eis.eis is EisCode.GEBIEDSBESCHERMING)
    if gebied.voldaan is None and invoer.gebiedsbescherming is Gebiedsbescherming.ONBEKEND:
        adviezen.append("Controleer de gebiedsaanduiding in het omgevingsplan.")
    if any(eis.voldaan is None for eis in eisen):
        adviezen.append("Vul de onbekende locatie- en maatgegevens in om de toets af te maken.")
    return " ".join(adviezen) or None


def _require_enum(name: str, value: object, expected: type[Enum]) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} moet een {expected.__name__} zijn")


def _require_optional_bool(name: str, value: object) -> None:
    if value is not None and type(value) is not bool:
        raise TypeError(f"{name} moet bool of None zijn")


def _require_optional_measurement(name: str, value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} moet Decimal of None zijn")
    if not value.is_finite():
        raise ValueError(f"{name} moet een eindige Decimal zijn")
    if value < 0:
        raise ValueError(f"{name} mag niet negatief zijn")


__all__ = [
    "VERGUNNINGCHECK_URL",
    "VOORBEHOUD_2_29",
    "ActiviteitResultaat",
    "Bbl_2_29_B_2_HOOGTE_MAX_M",
    "Bbl_2_29_B_3_ONDERZIJDE_MAX_M",
    "Bbl_2_29_B_3_ONDERZIJDE_MIN_M",
    "Bbl_2_29_B_4_BOVENZIJDE_MIN_M",
    "Bbl_2_29_B_5_ZIJKANT_MIN_M",
    "Bronverwijzing",
    "DakkapelInvoer",
    "Dakvlak",
    "EisCode",
    "EisResultaat",
    "Gebiedsbescherming",
    "Monumentrelatie",
    "Oordeel",
    "Toetsresultaat",
    "toets",
]
