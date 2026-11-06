"""Toestand-index: welke (bwb_id, artikel, onderdeel) bestaan in een BWB-toestand.

De index komt uit de echte toestand-XML's die ook de ingest-tests voeden
(zie `packages/nl-wetten-ingest/tests/fixtures/bwb_xml/`). Zo controleert de
datasetvalidator dat gouden bronnen écht bestaan in de geldende toestand
(issue #13), zonder database.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

StandaardToestanden = (
    _REPO_ROOT / "packages/nl-wetten-ingest/tests/fixtures/bwb_xml/bbl-2026-09-24.xml",
    _REPO_ROOT / "packages/nl-wetten-ingest/tests/fixtures/bwb_xml/awb-2026-08-15.xml",
)


@dataclass(frozen=True)
class ToestandIndex:
    """(bwb_id, artikel) -> verzameling onderdeelletters; lege set = artikel-zonder-letters."""

    bestanden: tuple[str, ...]
    artikelen: dict[tuple[str, str], frozenset[str]]

    def bestaat(self, bwb_id: str, artikel: str, onderdeel: str | None) -> bool:
        sleutel = (bwb_id, artikel)
        if sleutel not in self.artikelen:
            return False
        if onderdeel is None:
            return True
        return onderdeel in self.artikelen[sleutel]


def _norm(letter: str) -> str:
    return letter.strip().rstrip(".:").lower()


def bouw_index(paden: tuple[Path, ...]) -> ToestandIndex:
    """Lees toestand-XML's en indexeer artikelnummers met hun onderdeelletters."""
    artikelen: dict[tuple[str, str], set[str]] = {}
    for pad in paden:
        root = ET.parse(pad).getroot()
        bwb_id = root.get("bwb-id")
        if not bwb_id:
            msg = f"{pad}: geen bwb-id in de toestand"
            raise ValueError(msg)
        for artikel in root.iter("artikel"):
            nr = artikel.find("./kop/nr")
            label = nr.text.strip() if nr is not None and nr.text else ""
            if not label:
                continue
            sleutel = (bwb_id, label)
            letters = artikelen.setdefault(sleutel, set())
            for lijst in artikel.findall("./lijst"):
                for item in lijst.findall("./li"):
                    nummer = item.find("./li.nr")
                    if nummer is not None and nummer.text:
                        letters.add(_norm(nummer.text))
    return ToestandIndex(
        bestanden=tuple(str(pad) for pad in paden),
        artikelen={sleutel: frozenset(letters) for sleutel, letters in artikelen.items()},
    )
