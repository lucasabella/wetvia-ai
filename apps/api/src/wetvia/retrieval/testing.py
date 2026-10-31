"""Test doubles for the public retrieval port."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from wetvia.retrieval.ports import ScoredChunk, SourceDocument


class FakeRetriever:
    """Configured in-memory retriever for API and consumer tests."""

    def __init__(
        self,
        results: list[ScoredChunk] | None = None,
        sources: list[SourceDocument] | None = None,
    ) -> None:
        self.results = results or []
        source_by_id = {source.chunk_id: source for source in sources or []}
        source_by_id.update({result.source.chunk_id: result.source for result in self.results})
        self.sources = source_by_id
        self.search_calls: list[tuple[str, date, int, bool]] = []
        self.source_calls: list[tuple[UUID, date | None]] = []

    async def search(
        self,
        query: str,
        peildatum: date,
        k: int = 8,
        *,
        include_future: bool = False,
    ) -> list[ScoredChunk]:
        self.search_calls.append((query, peildatum, k, include_future))
        return self.results[:k]

    async def get_source(
        self,
        chunk_id: UUID,
        *,
        peildatum: date | None = None,
    ) -> SourceDocument | None:
        self.source_calls.append((chunk_id, peildatum))
        return self.sources.get(chunk_id)


__all__ = ["FakeRetriever"]
