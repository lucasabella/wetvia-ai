"""Synthetic-only tests for retrieval dataset validation, metrics, and reporting."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from wetvia.bootstrap import RetrieverRuntime
from wetvia.retrieval import ScoredChunk, SourceDocument, SourceMetadata
from wetvia.retrieval.testing import FakeRetriever
from wetvia_eval.retrieval_dataset import RetrievalEvalItem, load_retrieval_dataset
from wetvia_eval.retrieval_eval import (
    aggregate_metrics,
    evaluate_items,
    main,
    parse_fail_under,
    run_retrieval_command,
)
from wetvia_eval.retrieval_metrics import (
    ranked_unique_article_hits,
    score_article_retrieval,
)

_DATE = date(2026, 10, 31)
_GENERATED = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def _chunk(chunk_id: int, bwb_id: str, article: str) -> ScoredChunk:
    source = SourceDocument(
        chunk_id=UUID(int=chunk_id),
        tekst="Synthetic evaluation fixture; not legal text.",
        metadata=SourceMetadata(
            bwb_id=bwb_id,
            regeling_titel="Synthetic evaluation regulation (not legal text)",
            artikel=article,
            lid=None,
            onderdeel=None,
            opschrift=None,
            kop_pad="Synthetic fixture metadata",
            bron_url="https://example.test/synthetic-source",
            toestand_url="https://example.test/synthetic-state",
            geldig_vanaf=date(2020, 1, 1),
            geldig_tot=None,
            status="geldend",
            artikel_status="geldend",
        ),
    )
    return ScoredChunk(source=source, score=1.0 / (chunk_id + 1))


def _record(
    *,
    item_id: str = "concept-1",
    category: str = "A",
    sources: list[dict[str, object]] | None = None,
    peildatum: str = "2026-10-31",
    concept: bool = True,
) -> dict[str, object]:
    return {
        "id": item_id,
        "vraag": "synthetic query alpha",
        "categorie": category,
        "peildatum": peildatum,
        "verwachte_status": {
            "D": "buiten_scope",
            "F": "onzeker",
            "C": "onzeker",
        }.get(category, "beantwoord"),
        "kernfeiten": [],
        "gouden_bronnen": (
            [{"bwb_id": "TEST-REG", "artikel": "SYNTH-A", "onderdeel": None}]
            if sources is None
            else sources
        ),
        "concept": concept,
    }


def _item(**kwargs: object) -> RetrievalEvalItem:
    return RetrievalEvalItem.model_validate(_record(**kwargs))


def _write_dataset(path: Path, *records: dict[str, object]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _runtime_factory(retriever: FakeRetriever):
    @asynccontextmanager
    async def runtime() -> AsyncIterator[RetrieverRuntime]:
        yield RetrieverRuntime(retriever, "fixture/synthetic-embedder", 4)

    return runtime


def test_article_metrics_keep_original_chunk_ranks_and_dedupe_hits() -> None:
    gold = {("TEST-GOLD", "SYNTH-GOLD")}
    hits = [
        _chunk(1, "TEST-NON-GOLD", "SYNTH-NO"),
        _chunk(2, "TEST-NON-GOLD", "SYNTH-NO"),
        _chunk(3, "TEST-GOLD", "SYNTH-GOLD"),
    ]

    metrics = score_article_retrieval(gold, hits)
    ranked_articles = ranked_unique_article_hits(hits)

    assert metrics.recall_at_1 == 0.0
    assert metrics.recall_at_5 == 1.0
    assert metrics.recall_at_8 == 1.0
    assert metrics.mrr == pytest.approx(1 / 3)
    assert metrics.first_relevant_rank == 3
    assert [rank for rank, _ in ranked_articles] == [1, 3]


def test_duplicate_chunks_of_one_gold_article_do_not_inflate_recall() -> None:
    gold = {("TEST-GOLD", "SYNTH-A"), ("TEST-GOLD", "SYNTH-B")}
    hits = [
        _chunk(1, "TEST-GOLD", "SYNTH-A"),
        _chunk(2, "TEST-GOLD", "SYNTH-A"),
        _chunk(3, "TEST-GOLD", "SYNTH-B"),
    ]

    metrics = score_article_retrieval(gold, hits)

    assert metrics.recall_at_1 == 0.5
    assert metrics.recall_at_5 == 1.0
    assert metrics.first_relevant_rank == 1
    assert metrics.mrr == 1.0


def test_dataset_loader_validates_concept_marker_date_and_sources(tmp_path: Path) -> None:
    dataset = tmp_path / "synthetic.jsonl"
    _write_dataset(dataset, _record())

    loaded = load_retrieval_dataset(dataset)

    assert loaded[0].concept is True
    assert loaded[0].peildatum == _DATE
    assert loaded[0].golden_articles == frozenset({("TEST-REG", "SYNTH-A")})


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (_record(peildatum="2026-1-31"), "YYYY-MM-DD"),
        (_record(peildatum="2026-02-30"), "valid calendar date"),
        (_record(category="G"), "categorie"),
        (_record(sources=[{"bwb_id": "", "artikel": "SYNTH-A"}]), "bwb_id"),
        (_record(sources=[{"bwb_id": "TEST-REG", "artikel": " "}]), "artikel"),
        (_record(sources=[{"bwb_id": "TEST-REG", "artikel": "SYNTH-A"}]), "onderdeel"),
    ],
)
def test_dataset_loader_reports_line_for_invalid_fields(
    tmp_path: Path,
    record: dict[str, object],
    message: str,
) -> None:
    dataset = tmp_path / "invalid.jsonl"
    _write_dataset(dataset, record)

    with pytest.raises(ValueError, match=rf"invalid.jsonl:1:.*{message}"):
        load_retrieval_dataset(dataset)


def test_dataset_loader_rejects_duplicate_ids_with_line_number(tmp_path: Path) -> None:
    dataset = tmp_path / "duplicate.jsonl"
    _write_dataset(dataset, _record(), _record())

    with pytest.raises(ValueError, match=r"duplicate.jsonl:2: duplicate id 'concept-1'"):
        load_retrieval_dataset(dataset)


def test_dataset_loader_reports_json_errors_with_line_number(tmp_path: Path) -> None:
    dataset = tmp_path / "broken.jsonl"
    dataset.write_text(json.dumps(_record()) + "\n{bad json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"broken.jsonl:2: invalid JSON"):
        load_retrieval_dataset(dataset)


@pytest.mark.parametrize("missing_field", ["concept", "kernfeiten", "verwachte_status"])
def test_dataset_loader_requires_documented_fields_and_concept_marker(
    tmp_path: Path,
    missing_field: str,
) -> None:
    dataset = tmp_path / "missing-field.jsonl"
    record = _record()
    del record[missing_field]
    _write_dataset(dataset, record)

    with pytest.raises(
        ValueError, match=rf"missing-field.jsonl:1:.*{missing_field}: Field required"
    ):
        load_retrieval_dataset(dataset)


def test_dataset_loader_requires_concept_to_be_a_boolean(tmp_path: Path) -> None:
    dataset = tmp_path / "invalid-concept.jsonl"
    record = _record()
    record["concept"] = "false"
    _write_dataset(dataset, record)

    with pytest.raises(
        ValueError,
        match=r"invalid-concept.jsonl:1:.*concept: Input should be a valid boolean",
    ):
        load_retrieval_dataset(dataset)


def test_fail_under_accepts_only_finite_values_in_unit_interval() -> None:
    assert parse_fail_under("0") == 0.0
    assert parse_fail_under("1") == 1.0
    for value in ("-0.01", "1.01", "nan", "inf", "not-a-number"):
        with pytest.raises(argparse.ArgumentTypeError, match="between 0 and 1"):
            parse_fail_under(value)


def test_aggregate_excludes_d_f_and_items_without_gold_sources() -> None:
    items = [
        _item(item_id="eligible"),
        _item(item_id="d-case", category="D"),
        _item(item_id="f-case", category="F"),
        _item(item_id="no-gold", category="B", sources=[]),
    ]
    hit = _chunk(1, "TEST-REG", "SYNTH-A")
    retriever = FakeRetriever(results=[hit])

    async def exercise():
        evaluations = await evaluate_items(retriever, items)
        summary = aggregate_metrics(evaluations, "hybrid")
        return evaluations, summary

    evaluations, summary = asyncio.run(exercise())
    assert summary.eligible_items == 1
    assert summary.recall_at_8 == 1.0
    assert [entry.exclusion_reason is None for entry in evaluations] == [True, False, False, False]
    assert len(retriever.search_calls) == 3


def test_runner_writes_auditable_markdown_and_json_reports(tmp_path: Path) -> None:
    dataset = tmp_path / "concept.jsonl"
    _write_dataset(dataset, _record())
    hit = _chunk(1, "TEST-REG", "SYNTH-A")
    retriever = FakeRetriever(results_by_mode={mode: [hit] for mode in ("fts", "vector", "hybrid")})

    artifacts = asyncio.run(
        run_retrieval_command(
            dataset_path=dataset,
            out_dir=tmp_path / "reports",
            fail_under=1.0,
            runtime_factory=_runtime_factory(retriever),
            generated_at=_GENERATED,
        )
    )

    assert artifacts.exit_code == 0
    assert artifacts.markdown_path.is_file()
    assert artifacts.json_path.is_file()
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["dataset"]["contains_concept_data"] is True
    assert payload["dataset"]["sha256"]
    assert payload["embedding_config"] == {"model_id": "fixture/synthetic-embedder", "dimension": 4}
    assert payload["summary"]["hybrid"]["overall"]["recall_at_8"] == 1.0
    assert payload["items"][0]["modes"]["fts"]["raw_chunk_hits"][0]["artikel"] == "SYNTH-A"
    assert "CONCEPTDATA" in artifacts.markdown_path.read_text(encoding="utf-8")
    assert [call[-1] for call in retriever.search_calls] == ["fts", "vector", "hybrid"]


def test_main_writes_reports_before_nonzero_threshold_exit(tmp_path: Path) -> None:
    dataset = tmp_path / "concept.jsonl"
    _write_dataset(dataset, _record())
    retriever = FakeRetriever()
    out_dir = tmp_path / "reports"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "retrieval",
                "--dataset",
                str(dataset),
                "--out-dir",
                str(out_dir),
                "--fail-under",
                "0.85",
            ],
            runtime_factory=_runtime_factory(retriever),
        )

    assert exc_info.value.code == 1
    assert list(out_dir.glob("retrieval-*.md"))
    assert list(out_dir.glob("retrieval-*.json"))


def test_no_eligible_items_are_reported_before_nonzero_exit(tmp_path: Path) -> None:
    dataset = tmp_path / "excluded.jsonl"
    _write_dataset(
        dataset,
        _record(item_id="d-case", category="D"),
        _record(item_id="f-case", category="F", sources=[]),
        _record(item_id="no-gold", category="B", sources=[]),
    )
    retriever = FakeRetriever()
    out_dir = tmp_path / "reports"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "retrieval",
                "--dataset",
                str(dataset),
                "--out-dir",
                str(out_dir),
                "--fail-under",
                "0.85",
            ],
            runtime_factory=_runtime_factory(retriever),
        )

    assert exc_info.value.code == 2
    reports = list(out_dir.glob("retrieval-*.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["counts"] == {
        "total_items": 3,
        "eligible_items": 0,
        "excluded": {"category_D": 1, "category_F": 1, "no_golden_sources": 1},
    }
    assert payload["threshold_reason"].startswith("no eligible items")
    assert retriever.search_calls == []
