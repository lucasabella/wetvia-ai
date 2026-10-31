"""Article-level retrieval evaluation, reporting, and CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from wetvia.bootstrap import RetrieverRuntime, open_retriever
from wetvia.retrieval import Retriever, ScoredChunk, SearchMode
from wetvia_eval.retrieval_dataset import (
    Category,
    RetrievalEvalItem,
    load_retrieval_dataset,
)
from wetvia_eval.retrieval_metrics import (
    METRIC_CUTOFFS,
    RetrievalMetrics,
    ranked_unique_article_hits,
    score_article_retrieval,
)

MODES: tuple[SearchMode, ...] = ("fts", "vector", "hybrid")
RETRIEVAL_CHUNK_LIMIT = 60
CATEGORIES: tuple[Category, ...] = ("A", "B", "C", "D", "E", "F")
RuntimeFactory = Callable[[], AbstractAsyncContextManager[RetrieverRuntime]]


@dataclass(frozen=True, slots=True)
class ModeEvaluation:
    """Raw chunks and article-level scores for one mode of one dataset item."""

    chunks: tuple[ScoredChunk, ...]
    article_hits: tuple[tuple[int, ScoredChunk], ...]
    metrics: RetrievalMetrics


@dataclass(frozen=True, slots=True)
class ItemEvaluation:
    item: RetrievalEvalItem
    exclusion_reason: str | None
    modes: dict[SearchMode, ModeEvaluation]


@dataclass(frozen=True, slots=True)
class AggregateMetrics:
    eligible_items: int
    recall_at_1: float | None
    recall_at_5: float | None
    recall_at_8: float | None
    mrr: float | None


@dataclass(frozen=True, slots=True)
class RunArtifacts:
    markdown_path: Path
    json_path: Path
    exit_code: int
    payload: dict[str, Any]


async def evaluate_items(
    retriever: Retriever,
    items: Sequence[RetrievalEvalItem],
) -> list[ItemEvaluation]:
    """Run all three retrieval modes for scoreable items and keep raw results."""
    evaluations: list[ItemEvaluation] = []
    for item in items:
        exclusion = exclusion_reason(item)
        if exclusion is not None:
            evaluations.append(ItemEvaluation(item, exclusion, {}))
            continue

        mode_results: dict[SearchMode, ModeEvaluation] = {}
        for mode in MODES:
            chunks = await retriever.search(
                item.vraag,
                item.peildatum,
                k=RETRIEVAL_CHUNK_LIMIT,
                mode=mode,
            )
            article_hits = ranked_unique_article_hits(chunks)
            mode_results[mode] = ModeEvaluation(
                chunks=tuple(chunks),
                article_hits=tuple(article_hits),
                metrics=score_article_retrieval(item.golden_articles, chunks),
            )
        evaluations.append(ItemEvaluation(item, None, mode_results))
    return evaluations


def exclusion_reason(item: RetrievalEvalItem) -> str | None:
    """Return the single denominator-exclusion reason, if the item is unscored."""
    if item.categorie == "D":
        return "category D (out of scope)"
    if item.categorie == "F":
        return "category F (prompt injection / unsafe)"
    if not item.golden_articles:
        return "no golden articles"
    return None


def aggregate_metrics(
    evaluations: Sequence[ItemEvaluation],
    mode: SearchMode,
    *,
    category: Category | None = None,
) -> AggregateMetrics:
    """Macro-average per-item article recall and MRR for eligible examples."""
    selected = [
        evaluation
        for evaluation in evaluations
        if evaluation.exclusion_reason is None
        and mode in evaluation.modes
        and (category is None or evaluation.item.categorie == category)
    ]
    if not selected:
        return AggregateMetrics(0, None, None, None, None)
    metrics = [evaluation.modes[mode].metrics for evaluation in selected]
    return AggregateMetrics(
        eligible_items=len(metrics),
        recall_at_1=_mean_metric(metrics, "recall_at_1"),
        recall_at_5=_mean_metric(metrics, "recall_at_5"),
        recall_at_8=_mean_metric(metrics, "recall_at_8"),
        mrr=_mean_metric(metrics, "mrr"),
    )


def _mean_metric(metrics: Sequence[RetrievalMetrics], field_name: str) -> float | None:
    values = [cast(float, getattr(metric, field_name)) for metric in metrics]
    if not values:
        return None
    return sum(values) / len(values)


async def run_retrieval_command(
    *,
    dataset_path: Path,
    out_dir: Path,
    fail_under: float | None = None,
    runtime_factory: RuntimeFactory = open_retriever,
    generated_at: datetime | None = None,
) -> RunArtifacts:
    """Load, evaluate, and write both reports before returning any gate failure."""
    if fail_under is not None and (not math.isfinite(fail_under) or not 0.0 <= fail_under <= 1.0):
        raise ValueError("--fail-under must be a number between 0 and 1")
    try:
        dataset_bytes = dataset_path.read_bytes()
    except OSError as exc:
        raise ValueError(f"dataset file cannot be read: {dataset_path}") from exc
    items = load_retrieval_dataset(dataset_path, raw_bytes=dataset_bytes)
    dataset_hash = hashlib.sha256(dataset_bytes).hexdigest()
    timestamp = generated_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    timestamp = timestamp.astimezone(UTC)

    async with runtime_factory() as runtime:
        evaluations = await evaluate_items(runtime.retriever, items)
        payload = build_report_payload(
            dataset_path=dataset_path,
            dataset_hash=dataset_hash,
            items=items,
            evaluations=evaluations,
            model_id=runtime.model_id,
            dimension=runtime.dimension,
            generated_at=timestamp,
            fail_under=fail_under,
        )

    markdown = render_markdown_report(payload)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"retrieval-{stamp}"
    markdown_path = out_dir / f"{stem}.md"
    json_path = out_dir / f"{stem}.json"
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    no_eligible = payload["counts"]["eligible_items"] == 0
    threshold = payload["fail_under"]
    threshold_failed = threshold is not None and not payload["threshold_passed"]
    exit_code = 2 if no_eligible else (1 if threshold_failed else 0)
    return RunArtifacts(markdown_path, json_path, exit_code, payload)


def build_report_payload(
    *,
    dataset_path: Path,
    dataset_hash: str,
    items: Sequence[RetrievalEvalItem],
    evaluations: Sequence[ItemEvaluation],
    model_id: str,
    dimension: int,
    generated_at: datetime,
    fail_under: float | None,
) -> dict[str, Any]:
    eligible_items = sum(item.exclusion_reason is None for item in evaluations)
    excluded = {
        "category_D": sum(item.item.categorie == "D" for item in evaluations),
        "category_F": sum(item.item.categorie == "F" for item in evaluations),
        "no_golden_sources": sum(
            item.exclusion_reason == "no golden articles" for item in evaluations
        ),
    }
    summaries: dict[str, Any] = {}
    for mode in MODES:
        overall = aggregate_metrics(evaluations, mode)
        by_category = {
            category: _aggregate_payload(aggregate_metrics(evaluations, mode, category=category))
            for category in CATEGORIES
        }
        summaries[mode] = {
            "overall": _aggregate_payload(overall),
            "by_category": by_category,
        }

    hybrid_recall = summaries["hybrid"]["overall"]["recall_at_8"]
    if eligible_items == 0:
        threshold_passed = False
        threshold_reason = "no eligible items after excluding D/F and items without golden sources"
    elif fail_under is None:
        threshold_passed = None
        threshold_reason = None
    else:
        threshold_passed = hybrid_recall is not None and hybrid_recall >= fail_under
        threshold_reason = (
            None if threshold_passed else "overall hybrid recall@8 is below --fail-under"
        )

    concept_count = sum(item.concept for item in items)
    return {
        "schema_version": 1,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "dataset": {
            "path": str(dataset_path),
            "sha256": dataset_hash,
            "item_count": len(items),
            "concept_item_count": concept_count,
            "contains_concept_data": concept_count > 0,
        },
        "embedding_config": {"model_id": model_id, "dimension": dimension},
        "config": {
            "modes": list(MODES),
            "candidate_limit_per_mode": 30,
            "requested_chunks_per_query": RETRIEVAL_CHUNK_LIMIT,
            "article_metric_cutoffs": list(METRIC_CUTOFFS),
            "article_dedupe_key": ["bwb_id", "artikel"],
            "include_future": False,
            "aggregation": "macro average per eligible item",
        },
        "counts": {
            "total_items": len(items),
            "eligible_items": eligible_items,
            "excluded": excluded,
        },
        "fail_under": fail_under,
        "threshold_metric": "overall hybrid recall@8",
        "threshold_passed": threshold_passed,
        "threshold_reason": threshold_reason,
        "summary": summaries,
        "items": [_serialize_item(evaluation) for evaluation in evaluations],
    }


def _aggregate_payload(aggregate: AggregateMetrics) -> dict[str, int | float | None]:
    return asdict(aggregate)


def _serialize_item(evaluation: ItemEvaluation) -> dict[str, Any]:
    item = evaluation.item
    return {
        "id": item.id,
        "vraag": item.vraag,
        "categorie": item.categorie,
        "peildatum": item.peildatum.isoformat(),
        "verwachte_status": item.verwachte_status,
        "kernfeiten": list(item.kernfeiten),
        "concept": item.concept,
        "eligible": evaluation.exclusion_reason is None,
        "exclusion_reason": evaluation.exclusion_reason,
        "golden_articles": [
            {"bwb_id": bwb_id, "artikel": article}
            for bwb_id, article in sorted(item.golden_articles)
        ],
        "golden_sources": [source.model_dump(mode="json") for source in item.gouden_bronnen],
        "modes": {
            mode: {
                "metrics": asdict(mode_result.metrics),
                "article_ranking": [
                    {
                        "rank": rank,
                        "bwb_id": hit.source.metadata.bwb_id,
                        "artikel": hit.source.metadata.artikel,
                        "score": hit.score,
                        "chunk_id": str(hit.source.chunk_id),
                        "bron_url": hit.source.metadata.bron_url,
                        "toestand_url": hit.source.metadata.toestand_url,
                        "status": hit.source.metadata.status,
                        "artikel_status": hit.source.metadata.artikel_status,
                        "geldig_vanaf": hit.source.metadata.geldig_vanaf.isoformat(),
                        "geldig_tot": (
                            None
                            if hit.source.metadata.geldig_tot is None
                            else hit.source.metadata.geldig_tot.isoformat()
                        ),
                        "is_golden_article": (
                            hit.source.metadata.bwb_id,
                            hit.source.metadata.artikel,
                        )
                        in item.golden_articles,
                    }
                    for rank, hit in mode_result.article_hits
                ],
                "raw_chunk_hits": [
                    {
                        "rank": rank,
                        "chunk_id": str(hit.source.chunk_id),
                        "bwb_id": hit.source.metadata.bwb_id,
                        "artikel": hit.source.metadata.artikel,
                        "lid": hit.source.metadata.lid,
                        "onderdeel": hit.source.metadata.onderdeel,
                        "score": hit.score,
                        "bron_url": hit.source.metadata.bron_url,
                        "toestand_url": hit.source.metadata.toestand_url,
                        "status": hit.source.metadata.status,
                        "artikel_status": hit.source.metadata.artikel_status,
                        "geldig_vanaf": hit.source.metadata.geldig_vanaf.isoformat(),
                        "geldig_tot": (
                            None
                            if hit.source.metadata.geldig_tot is None
                            else hit.source.metadata.geldig_tot.isoformat()
                        ),
                    }
                    for rank, hit in enumerate(mode_result.chunks, start=1)
                ],
            }
            for mode, mode_result in evaluation.modes.items()
        },
    }


def render_markdown_report(payload: dict[str, Any]) -> str:
    dataset = payload["dataset"]
    counts = payload["counts"]
    lines = [
        "# Retrieval-evaluatie",
        "",
        f"- Gegenereerd: `{payload['generated_at_utc']}`",
        f"- Dataset: `{dataset['path']}`",
        f"- SHA-256: `{dataset['sha256']}`",
        f"- Geconfigureerd querymodel: `{payload['embedding_config']['model_id']}` "
        f"(dimensie {payload['embedding_config']['dimension']})",
        f"- Gevraagde chunks per query: {payload['config']['requested_chunks_per_query']}; "
        "metrics dedupliceren op `(bwb_id, artikel)`.",
        f"- Items: {counts['total_items']}; scorebaar: {counts['eligible_items']}; "
        f"uitgesloten D: {counts['excluded']['category_D']}, "
        f"F: {counts['excluded']['category_F']}, "
        f"zonder gouden bron: {counts['excluded']['no_golden_sources']}.",
        "",
        "Scores zijn macro-gemiddelden per scorebaar item. D/F en items zonder "
        "gouden artikelen tellen niet mee. Gebruik alleen een door mensen gecontroleerde "
        "dataset voor uitspraken over Wetvia-kwaliteit; issue #13 is daarvoor nog vereist.",
        "",
    ]
    if dataset["contains_concept_data"]:
        lines.extend(
            [
                "**CONCEPTDATA:** deze dataset bevat "
                f"{dataset['concept_item_count']} conceptitems. De scores zijn geen "
                "meting van Wetvia-kwaliteit.",
                "",
            ]
        )
    if payload["fail_under"] is not None:
        status = "gehaald" if payload["threshold_passed"] else "niet gehaald"
        lines.append(f"- Drempel: overall hybrid recall@8 ≥ {payload['fail_under']:.3f}: {status}.")
        if payload["threshold_reason"]:
            lines.append(f"- Drempelreden: {payload['threshold_reason']}.")
        lines.append("")
    elif counts["eligible_items"] == 0:
        lines.extend(
            [
                f"Geen scorebare items: {payload['threshold_reason']}.",
                "",
            ]
        )

    lines.extend(
        [
            "## Overall",
            "",
            "| Mode | Scorebare items | Recall@1 | Recall@5 | Recall@8 | MRR |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for mode in MODES:
        metrics = payload["summary"][mode]["overall"]
        lines.append(_summary_row(mode, metrics))

    lines.extend(
        [
            "",
            "## Per categorie",
            "",
            "| Categorie | Mode | Scorebare items | Recall@1 | Recall@5 | Recall@8 | MRR |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for category in CATEGORIES:
        for mode in MODES:
            metrics = payload["summary"][mode]["by_category"][category]
            lines.append(_summary_row(category, metrics, mode_column=mode))

    lines.extend(["", "## Per-item audit", ""])
    for item in payload["items"]:
        gold = (
            ", ".join(
                f"{source['bwb_id']}/{source['artikel']}" for source in item["golden_articles"]
            )
            or "geen gouden artikelen"
        )
        label = " concept" if item["concept"] else ""
        suffix = f" — uitgesloten: {item['exclusion_reason']}" if item["exclusion_reason"] else ""
        lines.append(
            f"### `{item['id']}` ({item['categorie']}{label}, peildatum "
            f"`{item['peildatum']}`){suffix}"
        )
        lines.append("")
        lines.append(f"Vraag: {item['vraag']}")
        lines.append(f"Gouden artikelen: {gold}.")
        for mode in MODES:
            mode_result = item["modes"].get(mode)
            if mode_result is None:
                lines.append(f"- {mode}: niet uitgevoerd.")
                continue
            ranking = mode_result["article_ranking"][:8]
            rendered = (
                ", ".join(
                    f"{entry['bwb_id']}/{entry['artikel']} (rank {entry['rank']})"
                    for entry in ranking
                )
                or "geen hits"
            )
            lines.append(f"- {mode}: {rendered}.")
        lines.append("")
    return "\n".join(lines)


def _summary_row(
    label: str,
    metrics: dict[str, Any],
    *,
    mode_column: str | None = None,
) -> str:
    cells = [label]
    if mode_column is not None:
        cells.append(mode_column)
    cells.extend(
        [
            str(metrics["eligible_items"]),
            _format_metric(metrics["recall_at_1"]),
            _format_metric(metrics["recall_at_5"]),
            _format_metric(metrics["recall_at_8"]),
            _format_metric(metrics["mrr"]),
        ]
    )
    return "| " + " | ".join(cells) + " |"


def _format_metric(value: float | None) -> str:
    return "niet gemeten" if value is None else f"{value:.3f}"


def parse_fail_under(value: str) -> float:
    """Argparse converter for a finite threshold in the inclusive interval [0, 1]."""
    try:
        threshold = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--fail-under must be a number between 0 and 1") from exc
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise argparse.ArgumentTypeError("--fail-under must be a number between 0 and 1")
    return threshold


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wetvia-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    retrieval = subparsers.add_parser(
        "retrieval",
        help="compare FTS, vector, and hybrid search",
    )
    retrieval.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="explicit JSONL dataset path",
    )
    retrieval.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    retrieval.add_argument("--fail-under", type=parse_fail_under)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runtime_factory: RuntimeFactory = open_retriever,
) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "retrieval":
        parser.error("a supported subcommand is required")
    try:
        artifacts = asyncio.run(
            run_retrieval_command(
                dataset_path=args.dataset,
                out_dir=args.out_dir,
                fail_under=args.fail_under,
                runtime_factory=runtime_factory,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Markdown report: {artifacts.markdown_path}")
    print(f"JSON report: {artifacts.json_path}")
    if artifacts.exit_code:
        print(artifacts.payload["threshold_reason"] or "no eligible eval items")
        raise SystemExit(artifacts.exit_code)


__all__ = [
    "AggregateMetrics",
    "ItemEvaluation",
    "ModeEvaluation",
    "RunArtifacts",
    "aggregate_metrics",
    "build_parser",
    "build_report_payload",
    "evaluate_items",
    "exclusion_reason",
    "main",
    "parse_fail_under",
    "render_markdown_report",
    "run_retrieval_command",
]
