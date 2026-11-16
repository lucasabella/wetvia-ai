"""Nakijken zonder model. Gesloten vragen: het antwoord moet het veld raken."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from nl_overheid_benchmark.items import BenchItem

_LABEL = re.compile(r"^(artikel|document|nummer|kenmerk)\s+", re.IGNORECASE)
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class AnswerScore:
    """`bron_goed` is None als het model geen bron meegaf en geen citaat."""

    antwoord_goed: bool
    bron_goed: bool | None
    gegeven_antwoord: str
    gegeven_bron: str | None
    gegeven_citaat: str | None


def normalize(value: str) -> str:
    text = value.casefold().strip()
    text = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2019", "'")
        .replace("\u2018", "'")
    )
    text = _SPACE.sub(" ", text)
    return text.strip(" .;:")


def _core(value: str) -> str:
    return _LABEL.sub("", normalize(value))


def _bounded(text: str, needle: str) -> bool:
    if not needle:
        return False
    return re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", text) is not None


def extract_fields(raw: str) -> tuple[str, str | None, str | None]:
    """Haal antwoord, bron en citaat uit JSON. Lukt dat niet, dan is de hele tekst het antwoord."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return raw.strip(), None, None
    try:
        parsed: object = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return raw.strip(), None, None
    if not isinstance(parsed, dict):
        return raw.strip(), None, None
    antwoord = parsed.get("antwoord")
    bron = parsed.get("bron")
    citaat = parsed.get("citaat")
    given = antwoord.strip() if isinstance(antwoord, str) else raw.strip()
    given_bron = bron.strip() if isinstance(bron, str) and bron.strip() else None
    given_citaat = citaat.strip() if isinstance(citaat, str) and citaat.strip() else None
    return given, given_bron, given_citaat


def answers_match(given: str, item: BenchItem) -> bool:
    if item.type == "open":
        return False
    left = _core(given)
    right = _core(item.antwoord)
    if left == right:
        return True
    options = tuple(_core(option) for option in item.opties)
    if options:
        mentioned = [option for option in options if _bounded(left, option)]
        return mentioned == [right]
    return _bounded(left, right) and len(left) <= len(right) + 40


def citation_matches(item: BenchItem, bron: str | None, citaat: str | None) -> bool | None:
    if bron is None and citaat is None:
        return None
    if citaat is not None and _core(citaat) not in _core(item.brontekst):
        return False
    if bron is None:
        return True
    return _core(bron) == _core(item.bron_label)


def score_response(item: BenchItem, raw: str) -> AnswerScore:
    gegeven, bron, citaat = extract_fields(raw)
    return AnswerScore(
        antwoord_goed=answers_match(gegeven, item),
        bron_goed=citation_matches(item, bron, citaat),
        gegeven_antwoord=gegeven,
        gegeven_bron=bron,
        gegeven_citaat=citaat,
    )
