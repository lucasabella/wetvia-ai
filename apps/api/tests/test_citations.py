"""Pure citation-verifier regression tests."""

from __future__ import annotations

import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from wetvia.citations import (
    CitationClaim,
    CitationSource,
    extract_measurements,
    retrieval_score_below_tau,
    verify_citations,
)


def _source(
    number: int = 1,
    *,
    text: str = "Synthetic source records 1,75 m.",
    start: date | str = date(2026, 1, 1),
    end: date | str | None = None,
    status: str = "geldend",
    article_status: str = "geldend",
) -> CitationSource:
    return CitationSource(
        chunk_id=UUID(int=number),
        text=text,
        geldig_vanaf=start,
        geldig_tot=end,
        status=status,
        artikel_status=article_status,
    )


def test_extract_measurements_normalizes_decimal_and_unit_aliases() -> None:
    assert extract_measurements("1,75 m; 1.750 meter; 30 cm²; artikel 2.29") == frozenset(
        {
            (Decimal("1.75"), "m"),
            (Decimal("30"), "cm²"),
        }
    )


def test_verifier_removes_point_with_mixed_known_and_unknown_source_ids() -> None:
    valid = _source()
    unknown = UUID(int=99)
    result = verify_citations(
        [CitationClaim("Synthetic point states 1.750 meter.", (unknown, valid.chunk_id))],
        {valid.chunk_id: valid},
        date(2026, 1, 1),
    )

    assert result.verified_claims == ()
    assert result.removed_count == 1
    assert any("unknown source ID removed" in note for note in result.notes)
    assert any("at least one source ID was unknown" in note for note in result.notes)


def test_verifier_removes_unsupported_number_measure_pair() -> None:
    source = _source(text="Synthetic source records 1.75 m.")
    result = verify_citations(
        [CitationClaim("Synthetic point records 1.50 m.", (source.chunk_id,))],
        {source.chunk_id: source},
        date(2026, 10, 31),
    )

    assert result.verified_claims == ()
    assert result.removed_count == 1
    assert "unsupported measurements 1.5 m" in result.notes[0]
    assert result.strict_majority_removed


@pytest.mark.parametrize(
    ("source", "expected_note"),
    [
        (_source(start="not-a-date"), "invalid source dates"),
        (_source(start=date(2026, 2, 1), end=date(2026, 1, 1)), "invalid source date range"),
        (_source(start=date(2026, 2, 1), end=date(2026, 12, 31)), "source invalid on peildatum"),
        (_source(status="vervallen"), "repealed source removed"),
        (_source(article_status="vervallen"), "repealed source removed"),
    ],
)
def test_invalid_dates_future_sources_and_repealed_articles_are_removed(
    source: CitationSource,
    expected_note: str,
) -> None:
    result = verify_citations(
        [CitationClaim("Synthetic claim.", (source.chunk_id,))],
        {source.chunk_id: source},
        date(2026, 1, 31),
    )

    assert result.verified_claims == ()
    assert result.removed_count == 1
    assert any(expected_note in note for note in result.notes)


def test_validity_boundaries_are_inclusive_and_invalid_peildatum_fails_closed() -> None:
    source = _source(start=date(2026, 1, 1), end=date(2026, 1, 31))
    sources = {source.chunk_id: source}
    claim = CitationClaim("Synthetic claim.", (source.chunk_id,))

    first_day = verify_citations([claim], sources, date(2026, 1, 1))
    last_day = verify_citations([claim], sources, date(2026, 1, 31))
    assert first_day.removed_count == 0
    assert last_day.removed_count == 0

    invalid = verify_citations([claim], sources, "2026-02-30")
    datetime_value = verify_citations([claim], sources, datetime(2026, 1, 31))
    assert invalid.verified_claims == datetime_value.verified_claims == ()
    assert invalid.removed_count == datetime_value.removed_count == 1
    assert "invalid peildatum" in invalid.notes[0]


def test_majority_rule_is_strict_not_inclusive() -> None:
    source = _source()
    sources = {source.chunk_id: source}
    supported = CitationClaim("Synthetic point states 1,75 m.", (source.chunk_id,))
    unsupported = CitationClaim("Synthetic point states 2,00 m.", (source.chunk_id,))

    half = verify_citations([supported, unsupported], sources, date(2026, 10, 31))
    majority = verify_citations([supported, unsupported, unsupported], sources, date(2026, 10, 31))
    assert half.removed_count == 1
    assert not half.strict_majority_removed
    assert majority.removed_count == 2
    assert majority.strict_majority_removed


def test_retrieval_threshold_uses_strict_comparison_and_fails_closed_on_nan() -> None:
    assert retrieval_score_below_tau(0.009, 0.01)
    assert not retrieval_score_below_tau(0.01, 0.01)
    assert retrieval_score_below_tau(float("nan"), 0.01)
    with pytest.raises(ValueError, match="tau"):
        retrieval_score_below_tau(0.1, -0.1)


def test_citations_module_has_no_answer_or_retrieval_imports() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "wetvia" / "citations"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith(("wetvia.answer", "wetvia.retrieval"))
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith(("wetvia.answer", "wetvia.retrieval"))
                    for alias in node.names
                )
