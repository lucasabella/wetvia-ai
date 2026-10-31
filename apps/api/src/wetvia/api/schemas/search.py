"""HTTP request and response models for legal search and sources."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

LegalStatus = Literal["geldend", "toekomstig", "vervallen"]
ArticleStatus = Literal["geldend", "vervallen"]


class SourceMetadataResponse(BaseModel):
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


class SourceDocumentResponse(BaseModel):
    chunk_id: UUID
    tekst: str
    metadata: SourceMetadataResponse


class ScoredChunkResponse(BaseModel):
    source: SourceDocumentResponse
    score: float


class SearchResponse(BaseModel):
    results: list[ScoredChunkResponse]


__all__ = [
    "ScoredChunkResponse",
    "SearchResponse",
    "SourceDocumentResponse",
    "SourceMetadataResponse",
]
