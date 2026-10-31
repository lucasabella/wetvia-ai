"""Synthetic-only tests for reviewed-dataset abstention calibration."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest

from wetvia.bootstrap import RetrieverRuntime
from wetvia.retrieval.testing import FakeRetriever
from wetvia_eval.tau_calibration import (
    CalibrationSample,
    calibrate_threshold,
    run_calibration,
)


def _record(
    *,
    concept: bool,
    item_id: str = "synthetic-f",
    category: str = "F",
    expected_status: str = "onzeker",
) -> dict[str, object]:
    return {
        "id": item_id,
        "vraag": "Synthetic test question, not a legal query.",
        "categorie": category,
        "peildatum": "2026-10-31",
        "verwachte_status": expected_status,
        "kernfeiten": [],
        "gouden_bronnen": [],
        "concept": concept,
    }


def test_calibration_maximizes_abstention_f1_with_strict_tau_boundary() -> None:
    result = calibrate_threshold(
        [
            CalibrationSample("reviewed-1", 0.01, True),
            CalibrationSample("reviewed-2", 0.10, True),
            CalibrationSample("reviewed-3", 0.15, False),
            CalibrationSample("reviewed-4", 0.20, False),
        ]
    )

    assert result.tau == pytest.approx(0.15)
    assert result.f1 == 1.0
    assert (result.true_positive, result.false_positive) == (2, 0)
    assert (result.false_negative, result.true_negative) == (0, 2)


def test_calibration_requires_valid_samples() -> None:
    with pytest.raises(ValueError, match="at least one"):
        calibrate_threshold([])
    with pytest.raises(ValueError, match="between 0 and 1"):
        calibrate_threshold([CalibrationSample("invalid", 1.1, True)])


def test_concept_data_is_rejected_before_opening_retriever(tmp_path: Path) -> None:
    dataset = tmp_path / "concept.jsonl"
    dataset.write_text(json.dumps(_record(concept=True)) + "\n", encoding="utf-8")

    def must_not_open():
        raise AssertionError("concept data must be rejected before retrieval")

    with pytest.raises(ValueError, match="refusing tau calibration on concept data"):
        asyncio.run(
            run_calibration(
                dataset_path=dataset,
                output_path=tmp_path / "report.json",
                runtime_factory=must_not_open,  # type: ignore[arg-type]
            )
        )


def test_calibration_writes_a_hashed_audit_report_with_public_retriever(tmp_path: Path) -> None:
    # This temporary synthetic row exercises report plumbing only. It is not an
    # eval dataset and its score is not a Wetvia quality measurement.
    dataset = tmp_path / "synthetic-reviewed.jsonl"
    raw = (
        json.dumps(_record(concept=False))
        + "\n"
        + json.dumps(
            _record(
                concept=False,
                item_id="synthetic-a",
                category="A",
                expected_status="beantwoord",
            )
        )
        + "\n"
    ).encode()
    dataset.write_bytes(raw)
    retriever = FakeRetriever(results=[])

    @asynccontextmanager
    async def runtime() -> AsyncIterator[RetrieverRuntime]:
        yield RetrieverRuntime(retriever, "fixture/synthetic", 1024)

    output = tmp_path / "reports" / "tau.json"
    artifacts = asyncio.run(
        run_calibration(
            dataset_path=dataset,
            output_path=output,
            runtime_factory=runtime,
        )
    )

    assert artifacts.output_path == output
    assert output.is_file()
    assert artifacts.payload["dataset_sha256"] == hashlib.sha256(raw).hexdigest()
    assert artifacts.payload["reviewed_item_count"] == 1
    assert artifacts.payload["status"] == "calibrated_on_caller_marked_reviewed_data"
    assert artifacts.payload["default_tau_status"] == "provisional_uncalibrated"
    assert artifacts.payload["retrieval_config"] == {
        "mode": "hybrid",
        "k": 8,
        "include_future": False,
        "query_embedding_model_id": "fixture/synthetic",
        "query_embedding_dimension": 1024,
    }
    assert artifacts.payload["item_counts"] == {
        "dataset_total": 2,
        "selected": 1,
        "selected_by_category": {"F": 1},
        "excluded": 1,
        "excluded_by_category": {"A": 1},
    }
    assert artifacts.payload["items"][0]["category"] == "F"
    assert artifacts.payload["items"][0]["expected_status"] == "onzeker"
    assert artifacts.payload["metrics"]["f1"] == 1.0
    assert retriever.search_calls == [
        ("Synthetic test question, not a legal query.", date(2026, 10, 31), 8, False, "hybrid")
    ]
