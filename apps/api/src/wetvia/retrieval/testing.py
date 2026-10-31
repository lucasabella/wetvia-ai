"""Test doubles for the public retrieval port."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from uuid import UUID

from wetvia.retrieval.ports import ScoredChunk, SearchMode, SourceDocument


class FakeRetriever:
    """Configured in-memory retriever for API and consumer tests."""

    def __init__(
        self,
        results: list[ScoredChunk] | None = None,
        sources: list[SourceDocument] | None = None,
        *,
        results_by_mode: Mapping[SearchMode, list[ScoredChunk]] | None = None,
    ) -> None:
        self.results = results or []
        self.results_by_mode = dict(results_by_mode or {})
        source_by_id = {source.chunk_id: source for source in sources or []}
        source_by_id.update({result.source.chunk_id: result.source for result in self.results})
        self.sources = source_by_id
        self.search_calls: list[tuple[str, date, int, bool, SearchMode]] = []
        self.source_calls: list[tuple[UUID, date | None]] = []

    async def search(
        self,
        query: str,
        peildatum: date,
        k: int = 8,
        *,
        include_future: bool = False,
        mode: SearchMode = "hybrid",
    ) -> list[ScoredChunk]:
        self.search_calls.append((query, peildatum, k, include_future, mode))
        return self.results_by_mode.get(mode, self.results)[:k]

    async def get_source(
        self,
        chunk_id: UUID,
        *,
        peildatum: date | None = None,
    ) -> SourceDocument | None:
        self.source_calls.append((chunk_id, peildatum))
        return self.sources.get(chunk_id)


__all__ = ["FakeRetriever"]
