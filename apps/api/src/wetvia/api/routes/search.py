"""Date-aware legal search and source lookup endpoints."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from wetvia.api.deps import get_retriever
from wetvia.api.schemas.search import (
    ScoredChunkResponse,
    SearchResponse,
    SourceDocumentResponse,
    SourceMetadataResponse,
)
from wetvia.retrieval import Retriever, ScoredChunk, SourceDocument

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_chunks(
    q: Annotated[str, Query(min_length=1, max_length=2000)],
    peildatum: date,
    retriever: Annotated[Retriever, Depends(get_retriever)],
    k: Annotated[int, Query(ge=1, le=60)] = 8,
    include_future: bool = False,
) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="q must not be blank")
    try:
        results = await retriever.search(
            q,
            peildatum,
            k,
            include_future=include_future,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search is unavailable because the embedding space is misconfigured.",
        ) from exc
    return SearchResponse(results=[_scored_response(result) for result in results])


@router.get("/sources/{chunk_id}", response_model=SourceDocumentResponse)
async def read_source(
    chunk_id: UUID,
    retriever: Annotated[Retriever, Depends(get_retriever)],
) -> SourceDocumentResponse:
    source = await retriever.get_source(chunk_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source chunk not found.")
    return _source_response(source)


def _scored_response(result: ScoredChunk) -> ScoredChunkResponse:
    return ScoredChunkResponse(source=_source_response(result.source), score=result.score)


def _source_response(source: SourceDocument) -> SourceDocumentResponse:
    return SourceDocumentResponse(
        chunk_id=source.chunk_id,
        tekst=source.tekst,
        metadata=SourceMetadataResponse.model_validate(source.metadata, from_attributes=True),
    )


__all__ = ["router"]
