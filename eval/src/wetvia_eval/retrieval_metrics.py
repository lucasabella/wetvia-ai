"""Pure article-level retrieval metrics shared by the runner and tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from wetvia.retrieval import ScoredChunk
from wetvia_eval.retrieval_dataset import ArticleKey

METRIC_CUTOFFS = (1, 5, 8)


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    """Per-query article recall and reciprocal rank; ``None`` means no gold articles."""

    recall_at_1: float | None
    recall_at_5: float | None
    recall_at_8: float | None
    mrr: float | None
    gold_article_count: int
    first_relevant_rank: int | None


def ranked_unique_article_hits(hits: Sequence[ScoredChunk]) -> list[tuple[int, ScoredChunk]]:
    """Keep each article's first chunk while retaining its original one-based rank."""
    unique: list[tuple[int, ScoredChunk]] = []
    seen: set[ArticleKey] = set()
    for rank, hit in enumerate(hits, start=1):
        metadata = hit.source.metadata
        key = metadata.bwb_id, metadata.artikel
        if key in seen:
            continue
        seen.add(key)
        unique.append((rank, hit))
    return unique


def score_article_retrieval(
    golden_articles: set[ArticleKey] | frozenset[ArticleKey],
    hits: Sequence[ScoredChunk],
) -> RetrievalMetrics:
    """Score distinct articles in rank order, so multiple chunks cannot inflate recall."""
    if not golden_articles:
        return RetrievalMetrics(None, None, None, None, 0, None)

    ranked_keys = [(hit.source.metadata.bwb_id, hit.source.metadata.artikel) for hit in hits]
    first_relevant_rank = next(
        (rank for rank, key in enumerate(ranked_keys, start=1) if key in golden_articles),
        None,
    )

    def recall_at(cutoff: int) -> float:
        found = {key for key in ranked_keys[:cutoff] if key in golden_articles}
        return len(found) / len(golden_articles)

    return RetrievalMetrics(
        recall_at_1=recall_at(1),
        recall_at_5=recall_at(5),
        recall_at_8=recall_at(8),
        mrr=0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank,
        gold_article_count=len(golden_articles),
        first_relevant_rank=first_relevant_rank,
    )
