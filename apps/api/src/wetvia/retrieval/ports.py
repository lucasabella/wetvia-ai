"""Public retrieval types and port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

LegalStatus = Literal["geldend", "toekomstig", "vervallen"]
ArticleStatus = Literal["geldend", "vervallen"]


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Legal provenance and validity attached to one parsed chunk."""

    bwb_id: str
    regeling_titel: str
    artikel: str
    lid: str | None
    onderdeel: str | None
    opschrift: str | None
    kop_pad: str
    bron_url: str
    toestand_url: str
    geldig_vanaf: date
    geldig_tot: date | None
    status: LegalStatus
    artikel_status: ArticleStatus


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """Chunk text and its source metadata, usable by search and citation UI."""

    chunk_id: UUID
    tekst: str
    metadata: SourceMetadata


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """One source document with its fused retrieval score."""

    source: SourceDocument
    score: float


class Retriever(Protocol):
    """Async read port for date-aware legal retrieval and source lookup."""

    async def search(
        self,
        query: str,
        peildatum: date,
        k: int = 8,
        *,
        include_future: bool = False,
    ) -> list[ScoredChunk]:
        """Return up to ``k`` relevant, date-valid source chunks."""

    async def get_source(
        self,
        chunk_id: UUID,
        *,
        peildatum: date | None = None,
    ) -> SourceDocument | None:
        """Return source content and provenance for a chunk UUID, if it exists."""


__all__ = [
    "ArticleStatus",
    "LegalStatus",
    "Retriever",
    "ScoredChunk",
    "SourceDocument",
    "SourceMetadata",
]
