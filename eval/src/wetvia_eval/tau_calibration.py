"""Choose a retrieval abstention threshold on a human-reviewed dataset."""

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
from typing import Any

from wetvia.bootstrap import RetrieverRuntime, open_retriever
from wetvia_eval.retrieval_dataset import load_retrieval_dataset

_CALIBRATION_CATEGORIES = frozenset({"C", "D", "F"})
_ABSTAIN_STATUSES = frozenset({"onzeker", "buiten_scope"})
_DEFAULT_TAU = 0.01
RuntimeFactory = Callable[[], AbstractAsyncContextManager[RetrieverRuntime]]


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    """One reviewed retrieval result and expected abstention label."""

    item_id: str
    best_score: float
    should_abstain: bool
    no_hits: bool = False
    category: str | None = None
    expected_status: str | None = None


@dataclass(frozen=True, slots=True)
class TauCalibration:
    """F1-optimal threshold and its confusion counts on calibration samples."""

    tau: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class CalibrationArtifacts:
    output_path: Path
    payload: dict[str, Any]


def calibrate_threshold(samples: Sequence[CalibrationSample]) -> TauCalibration:
    """Maximize abstention F1 over observed score boundaries in [0, 1].

    A score strictly below tau predicts abstention, and a no-hit result always
    abstains independently of tau. Ties select the lowest tau, minimizing extra
    abstentions when their F1 is equal.
    """
    if not samples:
        raise ValueError("at least one reviewed calibration sample is required")
    for sample in samples:
        if not sample.item_id.strip():
            raise ValueError("calibration sample IDs must be non-empty")
        if not math.isfinite(sample.best_score) or not 0.0 <= sample.best_score <= 1.0:
            raise ValueError("retrieval scores must be finite values between 0 and 1")
        if not isinstance(sample.should_abstain, bool):
            raise ValueError("expected abstention labels must be boolean")
        if not isinstance(sample.no_hits, bool):
            raise ValueError("no_hits must be boolean")

    maximum = max(sample.best_score for sample in samples)
    upper_boundary = min(1.0, math.nextafter(maximum, math.inf))
    thresholds = sorted({0.0, upper_boundary, *(sample.best_score for sample in samples)})
    candidates: list[TauCalibration] = []
    for tau in thresholds:
        true_positive = false_positive = false_negative = true_negative = 0
        for sample in samples:
            predicted = sample.no_hits or sample.best_score < tau
            if predicted and sample.should_abstain:
                true_positive += 1
            elif predicted:
                false_positive += 1
            elif sample.should_abstain:
                false_negative += 1
            else:
                true_negative += 1
        denominator = 2 * true_positive + false_positive + false_negative
        f1 = 0.0 if denominator == 0 else (2 * true_positive) / denominator
        candidates.append(
            TauCalibration(
                tau=tau,
                f1=f1,
                true_positive=true_positive,
                false_positive=false_positive,
                false_negative=false_negative,
                true_negative=true_negative,
                sample_count=len(samples),
            )
        )
    return max(candidates, key=lambda candidate: (candidate.f1, -candidate.tau))


async def run_calibration(
    *,
    dataset_path: Path,
    output_path: Path,
    runtime_factory: RuntimeFactory = open_retriever,
) -> CalibrationArtifacts:
    """Retrieve reviewed C/D/F items and write a reproducible tau report."""
    if not dataset_path.is_file():
        raise ValueError(f"dataset file does not exist: {dataset_path}")
    raw_bytes = dataset_path.read_bytes()
    items = load_retrieval_dataset(dataset_path, raw_bytes=raw_bytes)
    if not items:
        raise ValueError("cannot calibrate tau from an empty dataset")
    concept_ids = [item.id for item in items if item.concept]
    if concept_ids:
        preview = ", ".join(concept_ids[:5])
        raise ValueError(
            "refusing tau calibration on concept data; review every item and set "
            f"concept=false first (concept IDs: {preview})"
        )

    eligible = [item for item in items if item.categorie in _CALIBRATION_CATEGORIES]
    if not eligible:
        raise ValueError("tau calibration requires reviewed category C, D, or F items")
    excluded = [item for item in items if item.categorie not in _CALIBRATION_CATEGORIES]

    samples: list[CalibrationSample] = []
    model_id = "unknown"
    dimension = 0
    async with runtime_factory() as runtime:
        model_id = runtime.model_id
        dimension = runtime.dimension
        for item in eligible:
            hits = await runtime.retriever.search(
                item.vraag,
                item.peildatum,
                k=8,
                include_future=False,
                mode="hybrid",
            )
            no_hits = not hits
            best_score = max((hit.score for hit in hits), default=0.0)
            if not math.isfinite(best_score) or not 0.0 <= best_score <= 1.0:
                raise ValueError(f"retriever returned an invalid score for eval item {item.id!r}")
            samples.append(
                CalibrationSample(
                    item_id=item.id,
                    best_score=best_score,
                    should_abstain=item.verwachte_status in _ABSTAIN_STATUSES,
                    no_hits=no_hits,
                    category=item.categorie,
                    expected_status=item.verwachte_status,
                )
            )

    calibrated = calibrate_threshold(samples)
    payload: dict[str, Any] = {
        "status": "calibrated_on_caller_marked_reviewed_data",
        "dataset_review_status": "all_items_marked_concept_false",
        "dataset_review_note": (
            "The concept marker is caller-supplied and is not independently verified."
        ),
        "dataset_path": str(dataset_path),
        "dataset_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "created_at_utc": datetime.now(UTC).isoformat(),
        "calibration_categories": sorted(_CALIBRATION_CATEGORIES),
        "retrieval_config": {
            "mode": "hybrid",
            "k": 8,
            "include_future": False,
            "query_embedding_model_id": model_id,
            "query_embedding_dimension": dimension,
        },
        "item_counts": {
            "dataset_total": len(items),
            "selected": len(samples),
            "selected_by_category": {
                category: sum(item.categorie == category for item in eligible)
                for category in sorted({item.categorie for item in eligible})
            },
            "excluded": len(excluded),
            "no_hits": sum(sample.no_hits for sample in samples),
            "excluded_by_category": {
                category: sum(item.categorie == category for item in excluded)
                for category in sorted({item.categorie for item in excluded})
            },
        },
        "excluded_items": [
            {"id": item.id, "categorie": item.categorie, "reason": "category_not_in_allowlist"}
            for item in excluded
        ],
        "reviewed_item_count": len(samples),
        "threshold_rule": "no hits or best hybrid score < tau predicts abstention",
        "abstention_statuses": sorted(_ABSTAIN_STATUSES),
        "default_tau_before_calibration": _DEFAULT_TAU,
        "default_tau_status": "provisional_uncalibrated",
        "recommended_environment_variable": "ANSWER_ABSTENTION_TAU",
        "metrics": asdict(calibrated),
        "items": [asdict(sample) for sample in samples],
        "limitations": [
            "This is retrieval-score calibration for abstention only.",
            "It does not verify claim support or legal correctness.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return CalibrationArtifacts(output_path, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wetvia-calibrate-tau")
    parser.add_argument("--dataset", required=True, type=Path, help="human-reviewed JSONL dataset")
    parser.add_argument("--output", type=Path, help="JSON calibration report path")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runtime_factory: RuntimeFactory = open_retriever,
) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_path = args.output or _default_output_path()
    try:
        artifacts = asyncio.run(
            run_calibration(
                dataset_path=args.dataset,
                output_path=output_path,
                runtime_factory=runtime_factory,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Calibration report: {artifacts.output_path}")
    print(f"Recommended ANSWER_ABSTENTION_TAU={artifacts.payload['metrics']['tau']:.6g}")
    print(f"Abstention F1: {artifacts.payload['metrics']['f1']:.3f}")


def _default_output_path() -> Path:
    eval_root = Path(__file__).resolve().parents[2]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return eval_root / "reports" / f"tau-calibration-{timestamp}.json"


__all__ = [
    "CalibrationArtifacts",
    "CalibrationSample",
    "TauCalibration",
    "build_parser",
    "calibrate_threshold",
    "main",
    "run_calibration",
]
