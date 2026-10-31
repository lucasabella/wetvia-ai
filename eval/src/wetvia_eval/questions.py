"""JSONL-opzet voor de benchmark. De 30 vragen zelf zitten hier niet in."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BenchQuestion:
    id: str
    vraag: str
    brontekst: str


def load_questions(path: Path) -> list[BenchQuestion]:
    """Lees items. Extra velden uit docs/02 §6.1 (categorie, gouden bronnen) worden genegeerd."""
    if not path.is_file():
        return []
    questions: list[BenchQuestion] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed: object = json.loads(stripped)
        if not isinstance(parsed, dict):
            msg = f"{path}:{line_number} is geen JSON-object"
            raise ValueError(msg)
        vraag = parsed.get("vraag")
        item_id = parsed.get("id")
        if not isinstance(vraag, str) or not vraag.strip():
            msg = f"{path}:{line_number} mist een niet-lege string 'vraag'"
            raise ValueError(msg)
        if not isinstance(item_id, str) or not item_id.strip():
            msg = f"{path}:{line_number} mist een niet-lege string 'id'"
            raise ValueError(msg)
        brontekst = parsed.get("brontekst", "")
        if not isinstance(brontekst, str):
            msg = f"{path}:{line_number} veld 'brontekst' moet een string zijn"
            raise ValueError(msg)
        questions.append(BenchQuestion(id=item_id, vraag=vraag, brontekst=brontekst))
    return questions


def prompt_for(question: BenchQuestion) -> str:
    """Zonder RAG: alleen de brontekst uit het item gaat de prompt in."""
    bronnen = question.brontekst.strip() or "(geen brontekst in dit item)"
    return (
        "Antwoord alleen met JSON volgens het schema.\n"
        "Gebruik uitsluitend de BRONNEN. Staat het antwoord er niet in, "
        "zet status op onzeker.\n\n"
        f"VRAAG:\n{question.vraag.strip()}\n\n"
        f"BRONNEN:\n{bronnen}\n"
    )
