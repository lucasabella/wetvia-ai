"""JSONL-items voor de toets. Elk item wijst naar een bron. Geen verzonnen tekst."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

ITEM_TYPES = frozenset({"welk_artikel", "welk_document", "vast_feit", "meerkeuze", "open"})


@dataclass(frozen=True)
class BenchItem:
    id: str
    type: str
    vraag: str
    antwoord: str
    citaat: str
    brontekst: str
    bron_url: str
    bron_label: str
    concept: bool
    herkomst: str
    opties: tuple[str, ...] = ()
    peildatum: str | None = None


def concept_set_path() -> Path:
    """Pad naar de meegeleverde conceptset. Die is nog niet door een mens afgevinkt."""
    resource = files("nl_overheid_benchmark").joinpath("data/concept-v0.jsonl")
    return Path(str(resource))


def load_items(path: Path) -> list[BenchItem]:
    if not path.is_file():
        msg = f"{path} bestaat niet"
        raise ValueError(msg)
    items: list[BenchItem] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            parsed: object = json.loads(stripped)
        except json.JSONDecodeError as exc:
            msg = f"{path}:{line_number}: ongeldige JSON ({exc.msg})"
            raise ValueError(msg) from exc
        if not isinstance(parsed, dict):
            msg = f"{path}:{line_number}: is geen JSON-object"
            raise ValueError(msg)
        item = _item_from_object(path, line_number, parsed)
        if item.id in seen:
            msg = f"{path}:{line_number}: dubbele id {item.id!r}"
            raise ValueError(msg)
        seen.add(item.id)
        items.append(item)
    return items


def _require_str(path: Path, line_number: int, payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{path}:{line_number} mist een niet-lege string {key!r}"
        raise ValueError(msg)
    return value


def _item_from_object(path: Path, line_number: int, payload: dict[str, object]) -> BenchItem:
    item_type = _require_str(path, line_number, payload, "type")
    if item_type not in ITEM_TYPES:
        msg = f"{path}:{line_number}: onbekend type {item_type!r}"
        raise ValueError(msg)
    concept = payload.get("concept")
    if not isinstance(concept, bool):
        msg = f"{path}:{line_number} mist een boolean 'concept'"
        raise ValueError(msg)
    opties = _opties(path, line_number, payload)
    antwoord = _require_str(path, line_number, payload, "antwoord")
    if item_type == "meerkeuze" and antwoord not in opties:
        msg = f"{path}:{line_number}: het antwoord staat niet in de opties"
        raise ValueError(msg)
    peildatum = payload.get("peildatum")
    if peildatum is not None and not isinstance(peildatum, str):
        msg = f"{path}:{line_number} veld 'peildatum' moet een string zijn"
        raise ValueError(msg)
    return BenchItem(
        id=_require_str(path, line_number, payload, "id"),
        type=item_type,
        vraag=_require_str(path, line_number, payload, "vraag"),
        antwoord=antwoord,
        citaat=_require_str(path, line_number, payload, "citaat"),
        brontekst=_require_str(path, line_number, payload, "brontekst"),
        bron_url=_require_str(path, line_number, payload, "bron_url"),
        bron_label=_require_str(path, line_number, payload, "bron_label"),
        concept=concept,
        herkomst=_require_str(path, line_number, payload, "herkomst"),
        opties=tuple(opties),
        peildatum=peildatum,
    )


def _opties(path: Path, line_number: int, payload: dict[str, object]) -> list[str]:
    raw = payload.get("opties", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        msg = f"{path}:{line_number} veld 'opties' moet een lijst van strings zijn"
        raise ValueError(msg)
    options: list[str] = []
    for option in raw:
        if not isinstance(option, str) or not option.strip():
            msg = f"{path}:{line_number} veld 'opties' moet een lijst van strings zijn"
            raise ValueError(msg)
        options.append(option)
    if payload.get("type") == "meerkeuze" and len(options) < 2:
        msg = f"{path}:{line_number}: meerkeuze heeft minstens twee opties nodig"
        raise ValueError(msg)
    return options
