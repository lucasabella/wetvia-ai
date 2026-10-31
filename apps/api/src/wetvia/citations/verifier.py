"""Pure citation, validity-date, and measurement-pair checks."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

_MEASUREMENT_UNITS = (
    "millimeters?",
    "centimeters?",
    "kilometers?",
    "meters?",
    "millimeter",
    "centimeter",
    "kilometer",
    "kilogram(?:men)?",
    "gram(?:men)?",
    "milliliter",
    "millilitre",
    "liter",
    "litre",
    "uur|uren",
    "minuut|minuten",
    "seconde|seconden",
    "graad|graden",
    "m[²2]",
    "cm[²2]",
    "m[³3]",
    "cm[³3]",
    "mm",
    "cm",
    "km",
    "kg",
    "ml",
    "cl",
    "dl",
    "l",
    "g",
    "m",
    "%",
    "°c",
)
_BARE_QUANTITIES = (
    "jaar",
    "jaren",
    "maand",
    "maanden",
    "week",
    "weken",
    "dag",
    "dagen",
    "woning",
    "woningen",
    "gebouw",
    "gebouwen",
    "bijgebouw",
    "bijgebouwen",
    "persoon",
    "personen",
    "mens",
    "mensen",
    "bouwlaag",
    "bouwlagen",
    "woonlaag",
    "woonlagen",
    "verdieping",
    "verdiepingen",
    "etage",
    "etages",
    "vergunning",
    "vergunningen",
)
_UNIT_PATTERN = "|".join(sorted(_MEASUREMENT_UNITS, key=len, reverse=True))
_BARE_QUANTITY_PATTERN = "|".join(sorted(_BARE_QUANTITIES, key=len, reverse=True))
_NUMBER_PATTERN = r"[+-]?\d+(?:[.,]\d+)?"
_MEASUREMENT_PATTERN = re.compile(
    rf"(?<![\w.-])(?P<number>{_NUMBER_PATTERN})\s*"
    rf"(?P<unit>{_UNIT_PATTERN})(?!\w)",
    re.IGNORECASE,
)
_BARE_QUANTITY_RE = re.compile(
    rf"(?<![\w.-])(?P<number>{_NUMBER_PATTERN})\s+"
    rf"(?P<unit>{_BARE_QUANTITY_PATTERN})(?!\w)",
    re.IGNORECASE,
)
_IDENTIFIER_PREFIX = re.compile(
    r"(?:artikel(?:nummer)?|art\.?|hoofdstuk|paragraaf|lid|onderdeel|bijlage|"
    r"ecli|bwb(?:[- ]?id)?|id|nr\.?|nummer)\s*(?:[:#]\s*)?\Z",
    re.IGNORECASE,
)
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_UNIT_ALIASES = {
    "millimeter": "mm",
    "millimeters": "mm",
    "centimeter": "cm",
    "centimeters": "cm",
    "kilometer": "km",
    "kilometers": "km",
    "meter": "m",
    "meters": "m",
    "kilogram": "kg",
    "kilogrammen": "kg",
    "gram": "g",
    "grammen": "g",
    "milliliter": "ml",
    "millilitre": "ml",
    "liter": "l",
    "litre": "l",
    "uur": "uur",
    "uren": "uur",
    "minuut": "minuut",
    "minuten": "minuut",
    "seconde": "seconde",
    "seconden": "seconde",
    "graad": "graad",
    "graden": "graad",
    "jaar": "jaar",
    "jaren": "jaar",
    "maand": "maand",
    "maanden": "maand",
    "week": "week",
    "weken": "week",
    "dag": "dag",
    "dagen": "dag",
    "woning": "woning",
    "woningen": "woning",
    "gebouw": "gebouw",
    "gebouwen": "gebouw",
    "bijgebouw": "bijgebouw",
    "bijgebouwen": "bijgebouw",
    "persoon": "persoon",
    "personen": "persoon",
    "mens": "mens",
    "mensen": "mens",
    "bouwlaag": "bouwlaag",
    "bouwlagen": "bouwlaag",
    "woonlaag": "woonlaag",
    "woonlagen": "woonlaag",
    "verdieping": "verdieping",
    "verdiepingen": "verdieping",
    "etage": "etage",
    "etages": "etage",
    "vergunning": "vergunning",
    "vergunningen": "vergunning",
    "m2": "m²",
    "cm2": "cm²",
    "m3": "m³",
    "cm3": "cm³",
    "°c": "°c",
}


@dataclass(frozen=True, slots=True)
class CitationSource:
    """Only the source facts needed by verification; no retrieval dependency."""

    chunk_id: UUID
    text: str
    geldig_vanaf: date | str
    geldig_tot: date | str | None
    status: str
    artikel_status: str


@dataclass(frozen=True, slots=True)
class CitationClaim:
    """One generated claim and its asserted chunk IDs."""

    text: str
    source_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class VerifiedClaim:
    """Claim index and the valid source IDs retained for that claim."""

    point_index: int
    source_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Pure verifier result; notes are for diagnostics, not model input."""

    verified_claims: tuple[VerifiedClaim, ...]
    removed_count: int
    notes: tuple[str, ...]

    @property
    def strict_majority_removed(self) -> bool:
        total = len(self.verified_claims) + self.removed_count
        return total > 0 and self.removed_count * 2 > total


def parse_iso_date(value: date | str) -> date | None:
    """Parse a date without accepting datetimes, loose ISO forms, or invalid days."""
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or _ISO_DATE_PATTERN.fullmatch(value) is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def extract_quantities(text: str) -> frozenset[tuple[Decimal, str]]:
    """Return normalized numeric measurements, counts, and time quantities.

    Bare quantities use a short legal-domain noun allowlist; arbitrary number/noun
    pairs are excluded so article references and identifiers do not become claims.
    """
    quantities: set[tuple[Decimal, str]] = set()
    for pattern in (_MEASUREMENT_PATTERN, _BARE_QUANTITY_RE):
        for match in pattern.finditer(text):
            if _identifier_precedes(text, match.start()):
                continue
            quantity = _normalized_quantity(match.group("number"), match.group("unit"))
            if quantity is not None:
                quantities.add(quantity)
    return frozenset(quantities)


def extract_measurements(text: str) -> frozenset[tuple[Decimal, str]]:
    """Backward-compatible name for normalized numeric quantity extraction."""
    return extract_quantities(text)


def _normalized_quantity(number_text: str, unit_text: str) -> tuple[Decimal, str] | None:
    try:
        number = Decimal(number_text.replace(",", "."))
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    return number.normalize(), _UNIT_ALIASES.get(unit_text.casefold(), unit_text.casefold())


def _identifier_precedes(text: str, number_start: int) -> bool:
    return _IDENTIFIER_PREFIX.search(text[max(0, number_start - 40) : number_start]) is not None


def verify_citations(
    claims: Sequence[CitationClaim],
    sources: Mapping[UUID, CitationSource],
    peildatum: date | str,
) -> VerificationResult:
    """Drop claims without known, date-valid, non-repealed supporting sources.

    Every explicit number/quantity pair in a claim must occur in at least one
    retained cited chunk. This is a narrow lexical check, not semantic entailment.
    """
    requested_date = parse_iso_date(peildatum)
    if requested_date is None:
        return VerificationResult(
            verified_claims=(),
            removed_count=len(claims),
            notes=("invalid peildatum; all claims were removed",),
        )

    verified: list[VerifiedClaim] = []
    notes: list[str] = []
    removed = 0
    for point_index, claim in enumerate(claims):
        if not claim.text.strip():
            notes.append(f"point[{point_index}] removed: empty claim text")
            removed += 1
            continue
        if not claim.source_ids:
            notes.append(f"point[{point_index}] removed: no source IDs")
            removed += 1
            continue

        retained_sources: list[CitationSource] = []
        retained_ids: list[UUID] = []
        seen_ids: set[UUID] = set()
        has_unknown_id = False
        for source_id in claim.source_ids:
            if source_id in seen_ids:
                notes.append(f"point[{point_index}] duplicate source ID removed: {source_id}")
                continue
            seen_ids.add(source_id)
            source = sources.get(source_id)
            if source is None:
                notes.append(f"point[{point_index}] unknown source ID removed: {source_id}")
                has_unknown_id = True
                continue
            start = parse_iso_date(source.geldig_vanaf)
            end = parse_iso_date(source.geldig_tot) if source.geldig_tot is not None else None
            if start is None or (source.geldig_tot is not None and end is None):
                notes.append(f"point[{point_index}] invalid source dates: {source_id}")
                continue
            if end is not None and end < start:
                notes.append(f"point[{point_index}] invalid source date range: {source_id}")
                continue
            if (
                source.status.strip().casefold() == "vervallen"
                or source.artikel_status.strip().casefold() == "vervallen"
            ):
                notes.append(f"point[{point_index}] repealed source removed: {source_id}")
                continue
            if requested_date < start or (end is not None and requested_date > end):
                notes.append(f"point[{point_index}] source invalid on peildatum: {source_id}")
                continue
            retained_sources.append(source)
            retained_ids.append(source_id)

        if has_unknown_id:
            notes.append(f"point[{point_index}] removed: at least one source ID was unknown")
            removed += 1
            continue
        if not retained_sources:
            notes.append(f"point[{point_index}] removed: no valid cited sources remain")
            removed += 1
            continue

        asserted_quantities = extract_quantities(claim.text)
        source_quantities = frozenset(
            measurement
            for source in retained_sources
            for measurement in extract_quantities(source.text)
        )
        unsupported = asserted_quantities - source_quantities
        if unsupported:
            formatted = ", ".join(
                f"{_format_decimal(number)} {unit}"
                for number, unit in sorted(unsupported, key=lambda item: (item[1], item[0]))
            )
            notes.append(f"point[{point_index}] removed: unsupported measurements {formatted}")
            removed += 1
            continue

        verified.append(VerifiedClaim(point_index, tuple(retained_ids)))

    return VerificationResult(tuple(verified), removed, tuple(notes))


def retrieval_score_below_tau(best_score: float, tau: float) -> bool:
    """Apply the strict retrieval abstention boundary; invalid numeric values fail closed."""
    if not math.isfinite(best_score):
        return True
    if not math.isfinite(tau) or tau < 0:
        raise ValueError("tau must be a finite non-negative number")
    return best_score < tau


def _format_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


__all__ = [
    "CitationClaim",
    "CitationSource",
    "VerificationResult",
    "VerifiedClaim",
    "extract_measurements",
    "extract_quantities",
    "parse_iso_date",
    "retrieval_score_below_tau",
    "verify_citations",
]
