"""A/B-benchmark: basismodel versus LoRA op kamervragen (issue #47).

Deterministische metrics: schema-validiteit, abstentie-recall, statusnauwkeurigheid,
citatie-ondersteuning en peildatum-overeenkomst. De drempels staan in docs/02 §7.
De vragen zijn conceptfixtures met `"concept": true`; ze meten gedrag, geen
juridische inhoud. Geen cijfer wordt verzonnen: zonder antwoord staat er
`niet gemeten`.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from wetvia.bootstrap import get_ollama_provider
from wetvia.llm import ChatMessage, LLMProvider
from wetvia_eval.schema import AnswerV1

ABSTENTION_TARGET_PP = 5.0
CITATION_TARGET_PP = 3.0
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_NUM_CTX = 8192
_GEHAAld = "gehaald"
_NIET_GEMETEN = "niet gemeten"
_ABSTENTION_STATUSES = {"onzeker", "buiten_scope"}
_VERWACHTE_STATUSEN = {"beantwoord", "onzeker"}


class ProbeDataError(ValueError):
    """De probe-set is onbruikbaar: kapotte structuur of geen conceptmarkering."""


@dataclass(frozen=True)
class ProbeSource:
    bron_id: str
    tekst: str


@dataclass(frozen=True)
class ProbeItem:
    id: str
    vraag: str
    bronnen: tuple[ProbeSource, ...]
    verwachte_status: str
    peildatum: str
    categorie: str

    @property
    def bron_ids(self) -> frozenset[str]:
        return frozenset(bron.bron_id for bron in self.bronnen)


@dataclass(frozen=True)
class ProbeVerdict:
    item_id: str
    schema_valid: bool
    status: str | None = None
    status_match: bool | None = None
    abstained: bool | None = None
    citation_supported: bool | None = None
    peildatum_match: bool | None = None
    error: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class ModelMetrics:
    model: str
    items_total: int
    answered_items: int
    schema_valid_pct: float | None
    abstention_recall_pct: float | None
    status_accuracy_pct: float | None
    citation_support_pct: float | None
    peildatum_match_pct: float | None


@dataclass
class ModelRun:
    model: str
    metrics: ModelMetrics
    verdicts: list[ProbeVerdict] = field(default_factory=list)


def _required_string(row: dict[str, Any], key: str, line_number: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"regel {line_number}: veld '{key}' moet een niet-lege string zijn"
        raise ProbeDataError(msg)
    return value


def load_probes(path: Path) -> list[ProbeItem]:
    """Lees probe-items. Elk item moet expliciet `"concept": true` dragen."""
    if not path.is_file():
        msg = f"Probe-set bestaat niet: {path}"
        raise ProbeDataError(msg)

    probes: list[ProbeItem] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row: object = json.loads(stripped)
        except json.JSONDecodeError as exc:
            msg = f"{path}: regel {line_number}: ongeldige JSON ({exc.msg})"
            raise ProbeDataError(msg) from exc
        if not isinstance(row, dict):
            msg = f"{path}: regel {line_number}: is geen JSON-object"
            raise ProbeDataError(msg)
        if row.get("concept") is not True:
            msg = (
                f"{path}: regel {line_number}: probe-items zijn conceptfixtures en moeten "
                'expliciet "concept": true dragen (zie eval/data/README.md)'
            )
            raise ProbeDataError(msg)

        item_id = _required_string(row, "id", line_number)
        if item_id in seen_ids:
            msg = f"{path}: regel {line_number}: dubbele id {item_id!r}"
            raise ProbeDataError(msg)
        seen_ids.add(item_id)

        verwachte_status = _required_string(row, "verwachte_status", line_number)
        if verwachte_status not in _VERWACHTE_STATUSEN:
            msg = (
                f"{path}: regel {line_number}: verwachte_status moet "
                f"een van {sorted(_VERWACHTE_STATUSEN)} zijn"
            )
            raise ProbeDataError(msg)

        raw_bronnen = row.get("bronnen")
        if not isinstance(raw_bronnen, list) or not raw_bronnen:
            msg = f"{path}: regel {line_number}: 'bronnen' moet een niet-lege lijst zijn"
            raise ProbeDataError(msg)
        bron_ids: set[str] = set()
        bronnen: list[ProbeSource] = []
        for bron_index, raw_bron in enumerate(raw_bronnen, start=1):
            if not isinstance(raw_bron, dict):
                msg = f"{path}: regel {line_number}: bron {bron_index} is geen object"
                raise ProbeDataError(msg)
            bron_id = _required_string(raw_bron, "bron_id", line_number)
            if bron_id in bron_ids:
                msg = f"{path}: regel {line_number}: dubbele bron_id {bron_id!r}"
                raise ProbeDataError(msg)
            bron_ids.add(bron_id)
            bronnen.append(
                ProbeSource(bron_id=bron_id, tekst=_required_string(raw_bron, "tekst", line_number))
            )

        peildatum = _required_string(row, "peildatum", line_number)
        try:
            datetime.strptime(peildatum, "%Y-%m-%d")
        except ValueError as exc:
            msg = f"{path}: regel {line_number}: peildatum moet YYYY-MM-DD zijn"
            raise ProbeDataError(msg) from exc

        probes.append(
            ProbeItem(
                id=item_id,
                vraag=_required_string(row, "vraag", line_number),
                bronnen=tuple(bronnen),
                verwachte_status=verwachte_status,
                peildatum=peildatum,
                categorie=_required_string(row, "categorie", line_number),
            )
        )
    if not probes:
        msg = f"{path} bevat geen probe-items"
        raise ProbeDataError(msg)
    return probes


def prompt_for_probe(item: ProbeItem) -> str:
    bronnen = "\n\n".join(f"[{bron.bron_id}] {bron.tekst.strip()}" for bron in item.bronnen)
    bronnen = bronnen or "(geen bronnen in dit item)"
    return (
        "Antwoord alleen met JSON volgens het schema.\n"
        "Gebruik uitsluitend de BRONNEN. Staat het antwoord er niet in, "
        "zet status op onzeker.\n"
        "Noem bij elk punt in `bron_ids` alleen bron-ID's die in de BRONNEN staan.\n\n"
        f"VRAAG:\n{item.vraag.strip()}\n\n"
        f"BRONNEN:\n{bronnen}\n"
    )


def score_response(item: ProbeItem, raw: str) -> ProbeVerdict:
    """Scoor één antwoord tegen één probe-item. Deterministisch, zonder model."""
    if not raw.strip():
        return ProbeVerdict(item_id=item.id, schema_valid=False, raw=raw, error="leeg antwoord")
    try:
        answer = AnswerV1.model_validate_json(raw)
    except ValueError:
        return ProbeVerdict(item_id=item.id, schema_valid=False, raw=raw)

    status = answer.status
    return ProbeVerdict(
        item_id=item.id,
        schema_valid=True,
        status=status,
        status_match=status == item.verwachte_status,
        abstained=status in _ABSTENTION_STATUSES if item.verwachte_status == "onzeker" else None,
        citation_supported=_citations_supported(item, answer),
        peildatum_match=answer.peildatum == item.peildatum,
        raw=raw,
    )


def _citations_supported(item: ProbeItem, answer: AnswerV1) -> bool | None:
    """Alleen op beantwoorde items: elk punt moet bestaande bron-ID's citeren."""
    if item.verwachte_status != "beantwoord" or answer.status != "beantwoord":
        return None
    if not answer.punten:
        return False
    bron_ids = item.bron_ids
    return all(bool(punt.bron_ids) and set(punt.bron_ids) <= bron_ids for punt in answer.punten)


def _percent(counter: int, total: int) -> float | None:
    if total == 0:
        return None
    return 100.0 * counter / total


def summarize(model: str, verdicts: Sequence[ProbeVerdict], total: int) -> ModelMetrics:
    scored = [verdict for verdict in verdicts if verdict.error is None]
    abstention = [verdict for verdict in scored if verdict.abstained is not None]
    status_scored = [verdict for verdict in scored if verdict.status_match is not None]
    citation = [verdict for verdict in scored if verdict.citation_supported is not None]
    peildatum = [verdict for verdict in scored if verdict.peildatum_match is not None]
    return ModelMetrics(
        model=model,
        items_total=total,
        answered_items=len(scored),
        schema_valid_pct=_percent(sum(1 for v in scored if v.schema_valid), len(scored)),
        abstention_recall_pct=_percent(sum(1 for v in abstention if v.abstained), len(abstention)),
        status_accuracy_pct=_percent(
            sum(1 for v in status_scored if v.status_match), len(status_scored)
        ),
        citation_support_pct=_percent(
            sum(1 for v in citation if v.citation_supported), len(citation)
        ),
        peildatum_match_pct=_percent(
            sum(1 for v in peildatum if v.peildatum_match), len(peildatum)
        ),
    )


async def _collect_answer(provider: LLMProvider, prompt: str) -> str:
    stream = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        schema=AnswerV1,
        stream=True,
        temperature=0.0,
    )
    if not isinstance(stream, AsyncIterator):
        msg = "LLM-provider gaf geen stream terug"
        raise RuntimeError(msg)
    parts: list[str] = []
    async for chunk in stream:
        if chunk:
            parts.append(chunk)
    return "".join(parts)


def _ask(provider: LLMProvider, prompt: str) -> tuple[str, str | None]:
    try:
        content = asyncio.run(_collect_answer(provider, prompt))
    except (httpx.HTTPError, RuntimeError) as exc:
        return "", f"{type(exc).__name__}: {exc}"
    if not content:
        return "", "lege stream"
    return content, None


def _installed_tags(base_url: str) -> list[str]:
    """Alleen het raster van geïnstalleerde tags; geen chat via deze route."""
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=5.0)
        response.raise_for_status()
        payload: object = response.json()
    except (httpx.HTTPError, ValueError):
        return []
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    return [name for entry in models if isinstance((name := entry.get("name")), str)]


def _run_model(
    model: str,
    probes: Sequence[ProbeItem],
    base_url: str,
    num_ctx: int,
    keep_alive: str,
    provider_factory: Callable[..., LLMProvider] = get_ollama_provider,
) -> ModelRun:
    """Draai één model over alle probe-items.

    Standaard `keep_alive="0"`: Ollama ontlaadt het model na iedere vraag, zodat
    op een 8 GB-GPU het volgende model niet tegen een volgebleven VRAM loopt.
    """

    provider = provider_factory(
        base_url=base_url, model=model, num_ctx=num_ctx, keep_alive=keep_alive, think=False
    )
    verdicts: list[ProbeVerdict] = []
    for item in probes:
        raw, error = _ask(provider, prompt_for_probe(item))
        if error is not None:
            verdicts.append(ProbeVerdict(item_id=item.id, schema_valid=False, error=error))
            continue
        verdicts.append(score_response(item, raw))
    return ModelRun(model=model, metrics=summarize(model, verdicts, len(probes)), verdicts=verdicts)


def _format_pct(value: float | None) -> str:
    return _NIET_GEMETEN if value is None else f"{value:.1f}%"


def _verdict_line(label: str, base: float | None, tuned: float | None, target: float) -> str:
    if base is None or tuned is None:
        return f"| {label} | {_format_pct(base)} | {_format_pct(tuned)} | +{target:g}pp | — |"
    delta = tuned - base
    uitkomst = "gehaald" if delta >= target else "niet gehaald"
    return f"| {label} | {base:.1f}% | {tuned:.1f}% | +{target:g}pp | {delta:+.1f}pp → {uitkomst} |"


_PLAIN_METRICS = (
    ("Schema-validiteit", "schema_valid_pct"),
    ("Statusnauwkeurigheid", "status_accuracy_pct"),
    ("Peildatum correct", "peildatum_match_pct"),
)


def render_report(
    *,
    when: datetime,
    base_url: str,
    num_ctx: int,
    keep_alive: str,
    questions_path: Path,
    questions_sha256: str,
    runs: Sequence[ModelRun],
) -> str:
    baseline, tuned = runs[0].metrics, runs[1].metrics
    lines = [
        "# A/B-benchmark basismodel vs. LoRA",
        "",
        "Uitvoer van `eval/run.py ab`. De probevragen zijn conceptfixtures: ze meten "
        "alleen gedrag (abstentie, citatievorm), geen juridische inhoud. Geen enkel "
        "cijfer is verzonnen; een cel `niet gemeten` betekent dat die run geen data "
        "leverde.",
        "",
        "## Methode",
        "",
        f"- Endpoint: `{base_url}` via de publieke `wetvia.llm`-port, streaming, `think` uit.",
        f"- Context: `num_ctx={num_ctx}`, temperatuur 0, `keep_alive={keep_alive}`; "
        "schema: dummy-`AnswerV1` (docs/02 §4).",
        f"- Probe-set: `{questions_path}` (sha256 `{questions_sha256[:16]}…`, concept).",
        "",
        "## Drempels (docs/02 §7)",
        "",
        "| Metriek | Basismodel | LoRA | Drempel | Uitkomst |",
        "|---|---|---|---|---|",
        _verdict_line(
            "Abstentie-recall",
            baseline.abstention_recall_pct,
            tuned.abstention_recall_pct,
            ABSTENTION_TARGET_PP,
        ),
        _verdict_line(
            "Citatie-ondersteuning",
            baseline.citation_support_pct,
            tuned.citation_support_pct,
            CITATION_TARGET_PP,
        ),
        "",
        "## Overige metrieken",
        "",
        "| Metriek | Basismodel | LoRA |",
        "|---|---|---|",
    ]
    for label, attr in _PLAIN_METRICS:
        lines.append(
            f"| {label} | {_format_pct(getattr(baseline, attr))} | "
            f"{_format_pct(getattr(tuned, attr))} |"
        )
    lines += [
        "",
        "## Per-item audit",
        "",
        "Volledige ruwe antwoorden staan in het JSON-rapport naast dit bestand. "
        "Items met een fout tellen niet mee in de noemer van hun metriek.",
    ]
    for run in runs:
        errors = [verdict for verdict in run.verdicts if verdict.error is not None]
        if errors:
            lines.append(f"- `{run.model}`: {len(errors)} item(s) met een fout.")
    return "\n".join(lines) + "\n"


def report_paths(directory: Path, when: datetime) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y-%m-%d-%H%M%S")
    return directory / f"ab-{stamp}.md", directory / f"ab-{stamp}.json"


def _run_to_json(run: ModelRun) -> dict[str, Any]:
    return {
        "model": run.model,
        "metrics": dict(run.metrics.__dict__),
        "items": [dict(verdict.__dict__) for verdict in run.verdicts],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, help="Ollama-tag van het basismodel")
    parser.add_argument("--tuned", required=True, help="Ollama-tag van het LoRA-model")
    parser.add_argument("--questions", type=Path, default=Path("eval/data/ab_kamervragen.jsonl"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX)
    parser.add_argument(
        "--keep-alive",
        default="0",
        help=(
            "Ollama keep_alive per vraag; default '0' ontlaadt na iedere vraag "
            "zodat op 8 GB de baseline en de LoRA nooit tegelijk in VRAM staan."
        ),
    )
    parser.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2

    try:
        probes = load_probes(args.questions)
    except ProbeDataError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 2

    tags = _installed_tags(args.base_url)
    if not tags:
        print(
            f"Fout: Ollama op {args.base_url} is niet bereikbaar of heeft geen modellen.",
            file=sys.stderr,
        )
        return 2
    for required in (args.baseline, args.tuned):
        if required not in tags:
            print(
                f"Fout: model {required!r} staat niet in Ollama. Beschikbaar: "
                f"{', '.join(sorted(tags))}",
                file=sys.stderr,
            )
            return 2

    questions_sha = hashlib.sha256(args.questions.read_bytes()).hexdigest()
    runs = [
        _run_model(args.baseline, probes, args.base_url, args.num_ctx, args.keep_alive),
        _run_model(args.tuned, probes, args.base_url, args.num_ctx, args.keep_alive),
    ]

    now = datetime.now(UTC)
    report_md, report_json = report_paths(args.out_dir, now)
    report_md.write_text(
        render_report(
            when=now,
            base_url=args.base_url,
            num_ctx=args.num_ctx,
            keep_alive=args.keep_alive,
            questions_path=args.questions,
            questions_sha256=questions_sha,
            runs=runs,
        ),
        encoding="utf-8",
    )
    payload = {
        "generated_at": now.isoformat(),
        "base_url": args.base_url,
        "num_ctx": args.num_ctx,
        "questions": str(args.questions),
        "questions_sha256": questions_sha,
        "runs": [_run_to_json(run) for run in runs],
    }
    report_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Rapport: {report_md}\nAuditdata: {report_json}")
    return 0
