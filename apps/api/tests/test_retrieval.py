"""Pure retrieval helpers and the in-memory retriever port implementation."""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID

import pytest

from wetvia.retrieval import ScoredChunk, SourceDocument, SourceMetadata
from wetvia.retrieval.adapters.pg import _validate_query_vector
from wetvia.retrieval.hybrid import extract_article_references
from wetvia.retrieval.rrf import reciprocal_rank_score
from wetvia.retrieval.testing import FakeRetriever


def _source() -> SourceDocument:
    return SourceDocument(
        chunk_id=UUID("0b51c232-803b-5f94-a83c-8e12f3990029"),
        tekst="Official fixture text.",
        metadata=SourceMetadata(
            bwb_id="BWBR0041297",
            regeling_titel="Besluit bouwwerken leefomgeving",
            artikel="2.29",
            lid=None,
            onderdeel="b",
            opschrift=None,
            kop_pad="Hoofdstuk 2",
            bron_url="https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.29",
            toestand_url="https://example.test/toestand",
            geldig_vanaf=date(2026, 9, 24),
            geldig_tot=None,
            status="geldend",
            artikel_status="geldend",
        ),
    )


def test_article_reference_extraction_requires_complete_number_boundaries() -> None:
    assert extract_article_references("Art. 2.29, 12.29, 2.29a; not 2.29ab or x2.29") == (
        "2.29",
        "12.29",
        "2.29a",
    )
    assert extract_article_references("2.290") == ("2.290",)
    assert extract_article_references("2.29 and 2.29") == ("2.29",)


def test_reciprocal_rank_score_uses_one_based_rank_and_k_60() -> None:
    assert reciprocal_rank_score(1) == pytest.approx(1 / 61)
    assert reciprocal_rank_score(30) == pytest.approx(1 / 90)
    with pytest.raises(ValueError, match="one-based"):
        reciprocal_rank_score(0)


@pytest.mark.parametrize(
    ("vectors", "expected_dimension", "message"),
    [
        ([], 2, "0 vectors for one query"),
        ([[1.0]], 2, "dimension 1; expected 2"),
        ([[float("nan"), 0.0]], 2, "non-finite"),
        ([[2.0, 0.0]], 2, "unit-normalized"),
    ],
)
def test_query_vector_boundary_rejects_malformed_embeddings(
    vectors: list[list[float]], expected_dimension: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _validate_query_vector(vectors, expected_dimension=expected_dimension)


def test_fake_retriever_supports_search_and_source_lookup() -> None:
    source = _source()
    retriever = FakeRetriever([ScoredChunk(source, score=0.5)])

    async def exercise() -> None:
        results = await retriever.search("height", date(2026, 10, 31), k=4)
        found = await retriever.get_source(source.chunk_id)

        assert results == [ScoredChunk(source, score=0.5)]
        assert found == source
        assert retriever.search_calls == [("height", date(2026, 10, 31), 4, False, "hybrid")]
        assert retriever.source_calls == [(source.chunk_id, None)]

    asyncio.run(exercise())


def test_fake_retriever_can_return_results_by_search_mode() -> None:
    source = _source()
    fts = ScoredChunk(source, score=0.25)
    vector = ScoredChunk(source, score=0.5)
    retriever = FakeRetriever(results_by_mode={"fts": [fts], "vector": [vector]})

    async def exercise() -> None:
        assert await retriever.search("query", date(2026, 10, 31), mode="fts") == [fts]
        assert await retriever.search("query", date(2026, 10, 31), mode="vector") == [vector]
        assert await retriever.search("query", date(2026, 10, 31)) == []

    asyncio.run(exercise())
