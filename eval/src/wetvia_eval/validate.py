"""Validatie van handmatige evaluatiedatasets vóór ze de eval in gaan.

De veldregels staan in `eval/data/README.md`. Het tooling-gedeelte hier is
agent-werk; de vragen zelf blijven menselijk werk (issues #13, #26).
De validator verzint geen wettekst of artikelnummers; de validator kijkt
alleen naar structuur, niet naar inhoud.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from wetvia_eval.ab_eval import load_probes

_CATEGORIE_RETRIEVAL = frozenset({"A", "B", "C", "D", "E", "F"})
_VERWACHTE_STATUSEN = frozenset({"beantwoord", "onzeker", "buiten_scope"})
_KINDS = frozenset({"bench", "retrieval", "ab"})


@dataclass
class DatasetReport:
    path: Path
    kind: str
    items: int = 0
    errors: list[str] = field(default_factory=list)
    per_categorie: dict[str, int] = field(default_factory=dict)
    per_status: dict[str, int] = field(default_factory=dict)
    concept_true: int = 0
    concept_false: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, line_number: int, message: str) -> None:
        self.errors.append(f"regel {line_number}: {message}")

    def render(self) -> str:
        lines = [f"{self.path} (datasetsoort: {self.kind})", ""]
        if self.items == 0:
            lines.append("Geen items gevonden; er is niets te valideren of te scoren.")
        else:
            lines.append(f"Items: {self.items} | fouten: {len(self.errors)}")
        if self.per_categorie:
            cats = ", ".join(f"{key} {count}" for key, count in sorted(self.per_categorie.items()))
            lines.append(f"categorieën: {cats}")
        if self.per_status:
            stats = ", ".join(f"{key} {count}" for key, count in sorted(self.per_status.items()))
            lines.append(f"verwachte_status: {stats}")
        if self.items:
            lines.append(f"concept: true {self.concept_true} | false {self.concept_false}")
            if self.concept_false:
                lines.append(
                    "Let op: items met concept=false tellen als Wetvia-kwaliteit; "
                    "zet die pas op false na menselijke controle."
                )
        if self.errors:
            lines.append("")
            lines.append("Fouten:")
            lines.extend(f"- {message}" for message in self.errors)
        return "\n".join(lines) + "\n"


def _load_jsonl(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    """Lees JSONL; fouten per regel, zonder de rest te blokkeren."""
    rows: list[tuple[int, dict[str, Any]]] = []
    errors: list[str] = []
    if not path.is_file():
        errors.append(f"dataset bestaat niet: {path}")
        return rows, errors
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            parsed: object = json.loads(stripped)
        except json.JSONDecodeError as exc:
            errors.append(f"regel {line_number}: ongeldige JSON ({exc.msg})")
            continue
        if not isinstance(parsed, dict):
            errors.append(f"regel {line_number}: is geen JSON-object")
            continue
        rows.append((line_number, parsed))
    return rows, errors


def _require_nonempty_string(
    report: DatasetReport, line_number: int, row: dict[str, Any], key: str
) -> None:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        report.error(line_number, f"veld '{key}' moet een niet-lege string zijn")


def _validate_golden_bronnen(
    report: DatasetReport, line_number: int, bronnen: object, verwachte_status: str
) -> None:
    if not isinstance(bronnen, list):
        report.error(line_number, "veld 'gouden_bronnen' moet een lijst zijn")
        return
    if verwachte_status == "beantwoord" and not bronnen:
        report.error(
            line_number, "'beantwoord' vereist ten minste één gouden bron (bwb_id + artikel)"
        )
    for index, bron in enumerate(bronnen, start=1):
        if not isinstance(bron, dict):
            report.error(line_number, f"gouden_bronnen[{index}] is geen object")
            continue
        if set(bron) != {"bwb_id", "artikel", "onderdeel"}:
            report.error(
                line_number,
                f"gouden_bronnen[{index}] heeft precies 'bwb_id', 'artikel' en "
                f"'onderdeel' nodig (kreeg {sorted(bron)})",
            )
            continue
        for key in ("bwb_id", "artikel"):
            value = bron.get(key)
            if not isinstance(value, str) or not value.strip():
                report.error(line_number, f"gouden_bronnen[{index}].{key} moet tekst zijn")
        onderdeel = bron.get("onderdeel")
        if onderdeel is not None and (not isinstance(onderdeel, str) or not onderdeel.strip()):
            report.error(line_number, f"gouden_bronnen[{index}].onderdeel is null of tekst")


def _detect_kind(rows: Sequence[dict[str, Any]]) -> str:
    for row in rows:
        if "gouden_bronnen" in row:
            return "retrieval"
        if isinstance(row.get("bronnen"), list):
            return "ab"
    return "bench"


def _validate_bench_row(report: DatasetReport, line_number: int, row: dict[str, Any]) -> None:
    """bench.jsonl: id + vraag verplicht, brontekst optioneel (zie load_questions)."""
    _require_nonempty_string(report, line_number, row, "id")
    _require_nonempty_string(report, line_number, row, "vraag")
    if "brontekst" in row and not isinstance(row["brontekst"], str):
        report.error(line_number, "veld 'brontekst' moet een string zijn")


def _validate_retrieval_row(report: DatasetReport, line_number: int, row: dict[str, Any]) -> None:
    """Gouden set: alle velden uit eval/data/README.md zijn verplicht."""
    _require_nonempty_string(report, line_number, row, "id")
    _require_nonempty_string(report, line_number, row, "vraag")

    categorie = row.get("categorie")
    if not isinstance(categorie, str) or not categorie.strip():
        report.error(line_number, "veld 'categorie' moet een niet-lege string zijn")
    elif categorie not in _CATEGORIE_RETRIEVAL:
        report.error(line_number, f"categorieën voor retrieval zijn A-F (kreeg {categorie!r})")
    else:
        report.per_categorie[categorie] = report.per_categorie.get(categorie, 0) + 1

    verwachte_status = row.get("verwachte_status")
    if not isinstance(verwachte_status, str) or verwachte_status not in _VERWACHTE_STATUSEN:
        report.error(
            line_number, f"verwachte_status moet een van {sorted(_VERWACHTE_STATUSEN)} zijn"
        )
        verwachte_status = ""
    else:
        report.per_status[verwachte_status] = report.per_status.get(verwachte_status, 0) + 1

    if "concept" not in row:
        report.error(line_number, "veld 'concept' is verplicht (true of false)")
    elif row["concept"] is True:
        report.concept_true += 1
    elif row["concept"] is False:
        report.concept_false += 1
    else:
        report.error(line_number, "veld 'concept' moet de boolean true of false zijn")

    peildatum = row.get("peildatum")
    if not isinstance(peildatum, str):
        report.error(line_number, "veld 'peildatum' moet YYYY-MM-DD zijn")
    else:
        try:
            datetime.strptime(peildatum, "%Y-%m-%d")
        except ValueError:
            report.error(line_number, "veld 'peildatum' moet YYYY-MM-DD zijn")

    if "kernfeiten" not in row:
        report.error(line_number, "veld 'kernfeiten' is verplicht")
    elif (
        not isinstance(row["kernfeiten"], list)
        or not row["kernfeiten"]
        or any(not isinstance(feit, str) or not feit.strip() for feit in row["kernfeiten"])
    ):
        report.error(line_number, "kernfeiten moet een lijst met niet-lege teksten zijn")

    if "gouden_bronnen" not in row:
        report.error(line_number, "veld 'gouden_bronnen' is verplicht")
    else:
        _validate_golden_bronnen(report, line_number, row["gouden_bronnen"], verwachte_status)


def validate_dataset(path: Path, kind: str | None = None) -> DatasetReport:
    """Valideer een datasetbestand. `kind=None` betekent automatisch afleiden."""
    rows, read_errors = _load_jsonl(path)
    if kind is None:
        kind = _detect_kind([row for _, row in rows])
    report = DatasetReport(path=path, kind=kind)
    report.errors.extend(read_errors)
    if kind not in _KINDS:
        report.errors.append(f"onbekende datasetsoort {kind!r}; kies uit {sorted(_KINDS)}")
        return report

    if kind == "ab":
        # Strengere probe-regels (concept verplicht true) staan in de loader.
        try:
            probes = load_probes(path)
        except ValueError as exc:
            report.errors.append(f"probe-validatie: {exc}")
            return report
        report.items = len(probes)
        for probe in probes:
            report.per_status[probe.verwachte_status] = (
                report.per_status.get(probe.verwachte_status, 0) + 1
            )
            report.per_categorie[probe.categorie] = report.per_categorie.get(probe.categorie, 0) + 1
        report.concept_true = len(probes)
        return report

    seen_ids: dict[str, int] = {}
    for line_number, row in rows:
        report.items += 1
        item_id = row.get("id")
        if isinstance(item_id, str) and item_id.strip():
            if item_id in seen_ids:
                report.error(
                    line_number,
                    f"dubbele id {item_id!r} (eerst gezien op regel {seen_ids[item_id]})",
                )
            seen_ids[item_id] = line_number
        if kind == "bench":
            _validate_bench_row(report, line_number, row)
        else:
            _validate_retrieval_row(report, line_number, row)

    if not rows:
        report.errors.append("dataset is leeg; ook een lege set hoort gemarkeerd te worden")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--kind",
        choices=sorted(_KINDS),
        default=None,
        help="datasetsoort; default: automatisch afleiden",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    report = validate_dataset(args.dataset, args.kind)
    print(report.render())
    return 0 if report.ok else 1
