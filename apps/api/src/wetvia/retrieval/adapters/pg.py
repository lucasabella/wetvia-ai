"""PostgreSQL hybrid retrieval using Dutch FTS, pgvector, and RRF."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from datetime import date
from math import isfinite, sqrt
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from wetvia.embeddings import Embedder, format_query_input
from wetvia.retrieval.hybrid import QUERY_INSTRUCTION, extract_article_references
from wetvia.retrieval.ports import (
    ArticleStatus,
    LegalStatus,
    ScoredChunk,
    SourceDocument,
    SourceMetadata,
)
from wetvia.retrieval.rrf import RRF_K

_VECTOR_TYPE = re.compile(r"vector\((\d+)\)")
_EMBEDDING_SPACE_SQL = text(
    """
    SELECT config.model_id, config.dimension,
           format_type(attribute.atttypid, attribute.atttypmod) AS vector_type
    FROM pg_attribute AS attribute
    LEFT JOIN embedding_config AS config ON config.id = 1
    WHERE attribute.attrelid = 'chunk'::regclass
      AND attribute.attname = 'embedding'
      AND NOT attribute.attisdropped
    """
)

_SEARCH_SQL = text(
    """
    WITH query_terms AS (
        SELECT websearch_to_tsquery('dutch', :query) AS tsquery
    ),
    fts_candidates AS (
        SELECT chunk.id,
               ts_rank_cd(chunk.tsv, query_terms.tsquery) AS relevance
        FROM chunk
        CROSS JOIN query_terms
        WHERE chunk.tsv @@ query_terms.tsquery
          AND chunk.artikel_status <> 'vervallen'
          AND (:include_future OR chunk.geldig_vanaf <= :peildatum)
          AND (chunk.geldig_tot IS NULL OR chunk.geldig_tot >= :peildatum)
        ORDER BY relevance DESC, chunk.id ASC
        LIMIT 30
    ),
    fts_ranked AS (
        SELECT id,
               row_number() OVER (ORDER BY relevance DESC, id ASC) AS position
        FROM fts_candidates
    ),
    vector_candidates AS (
        SELECT chunk.id,
               chunk.embedding <=> CAST(:query_vector AS vector) AS distance
        FROM chunk
        WHERE chunk.embedding IS NOT NULL
          AND chunk.artikel_status <> 'vervallen'
          AND (:include_future OR chunk.geldig_vanaf <= :peildatum)
          AND (chunk.geldig_tot IS NULL OR chunk.geldig_tot >= :peildatum)
        ORDER BY distance ASC, chunk.id ASC
        LIMIT 30
    ),
    vector_ranked AS (
        SELECT id,
               row_number() OVER (ORDER BY distance ASC, id ASC) AS position
        FROM vector_candidates
    ),
    article_candidates AS (
        SELECT chunk.id
        FROM chunk
        WHERE chunk.artikel_status <> 'vervallen'
          AND (:include_future OR chunk.geldig_vanaf <= :peildatum)
          AND (chunk.geldig_tot IS NULL OR chunk.geldig_tot >= :peildatum)
          AND lower(btrim(chunk.artikel)) = ANY(CAST(:article_refs AS text[]))
    ),
    candidate_ids AS (
        SELECT id FROM fts_ranked
        UNION
        SELECT id FROM vector_ranked
        UNION
        SELECT id FROM article_candidates
    ),
    fused_scores AS (
        SELECT ranked.id,
               sum(1.0 / (:rrf_k + ranked.position)) AS rrf_score
        FROM (
            SELECT id, position FROM fts_ranked
            UNION ALL
            SELECT id, position FROM vector_ranked
        ) AS ranked
        GROUP BY ranked.id
    )
    SELECT chunk.id AS chunk_id,
           chunk.tekst,
           chunk.bwb_id,
           chunk.regeling_titel,
           chunk.artikel,
           chunk.lid,
           chunk.onderdeel,
           chunk.opschrift,
           chunk.kop_pad,
           chunk.bron_url,
           chunk.toestand_url,
           chunk.geldig_vanaf,
           chunk.geldig_tot,
           chunk.artikel_status,
           CASE
               WHEN chunk.artikel_status = 'vervallen'
                    OR (chunk.geldig_tot IS NOT NULL AND chunk.geldig_tot < :peildatum)
                   THEN 'vervallen'
               WHEN chunk.geldig_vanaf > :peildatum THEN 'toekomstig'
               ELSE 'geldend'
           END AS effective_status,
           coalesce(fused_scores.rrf_score, 0.0)
               + CASE
                     WHEN lower(btrim(chunk.artikel)) = ANY(CAST(:article_refs AS text[]))
                         THEN :article_boost
                     ELSE 0.0
                 END AS score
    FROM candidate_ids
    JOIN chunk ON chunk.id = candidate_ids.id
    LEFT JOIN fused_scores ON fused_scores.id = chunk.id
    ORDER BY score DESC, chunk.id ASC
    LIMIT :limit
    """
)

_SOURCE_SQL = text(
    """
    SELECT chunk.id AS chunk_id,
           chunk.tekst,
           chunk.bwb_id,
           chunk.regeling_titel,
           chunk.artikel,
           chunk.lid,
           chunk.onderdeel,
           chunk.opschrift,
           chunk.kop_pad,
           chunk.bron_url,
           chunk.toestand_url,
           chunk.geldig_vanaf,
           chunk.geldig_tot,
           chunk.artikel_status,
           CASE
               WHEN chunk.artikel_status = 'vervallen'
                    OR (chunk.geldig_tot IS NOT NULL AND chunk.geldig_tot < :peildatum)
                   THEN 'vervallen'
               WHEN chunk.geldig_vanaf > :peildatum THEN 'toekomstig'
               ELSE 'geldend'
           END AS effective_status
    FROM chunk
    WHERE chunk.id = :chunk_id
    """
)


class PgHybridRetriever:
    """Search PostgreSQL using one FTS/vector CTE query and an injected embedder."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        *,
        query_instruction: str = QUERY_INSTRUCTION,
    ) -> None:
        if not query_instruction.strip():
            raise ValueError("query instruction must not be empty")
        self._sessions = sessions
        self._embedder = embedder
        self._query_instruction = query_instruction

    async def search(
        self,
        query: str,
        peildatum: date,
        k: int = 8,
        *,
        include_future: bool = False,
    ) -> list[ScoredChunk]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= k <= 60:
            raise ValueError("k must be between 1 and 60")

        await self._validate_embedding_space()
        formatted_query = format_query_input(self._query_instruction, query)
        vectors = await asyncio.to_thread(self._embedder.embed, [formatted_query])
        query_vector = _validate_query_vector(
            vectors,
            expected_dimension=self._embedder.dimension,
        )
        article_refs = list(extract_article_references(query))
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    _SEARCH_SQL,
                    {
                        "query": query,
                        "query_vector": str(query_vector),
                        "peildatum": peildatum,
                        "include_future": include_future,
                        "article_refs": article_refs,
                        "article_boost": 1.0,
                        "rrf_k": RRF_K,
                        "limit": k,
                    },
                )
            ).mappings()
            return [
                ScoredChunk(
                    source=_source_from_row(row),
                    score=float(row["score"]),
                )
                for row in rows
            ]

    async def get_source(
        self,
        chunk_id: UUID,
        *,
        peildatum: date | None = None,
    ) -> SourceDocument | None:
        async with self._sessions() as session:
            row = (
                (
                    await session.execute(
                        _SOURCE_SQL,
                        {"chunk_id": chunk_id, "peildatum": peildatum or date.today()},
                    )
                )
                .mappings()
                .one_or_none()
            )
        return None if row is None else _source_from_row(row)

    async def _validate_embedding_space(self) -> None:
        async with self._sessions() as session:
            row = (await session.execute(_EMBEDDING_SPACE_SQL)).mappings().one_or_none()
            if row is None:
                raise RuntimeError("PostgreSQL chunk.embedding column is missing")

            model_id = row["model_id"]
            dimension = row["dimension"]
            type_name = row["vector_type"]
        match = _VECTOR_TYPE.fullmatch(type_name or "")
        if match is None:
            raise RuntimeError("chunk.embedding must use a fixed-dimension PostgreSQL vector type")
        database_dimension = int(match.group(1))
        if model_id is None or dimension is None:
            raise ValueError("embedding_config is missing; embed the corpus before searching")
        if model_id != self._embedder.model_id or dimension != self._embedder.dimension:
            raise ValueError(
                f"stored vectors use {model_id!r} at dimension {dimension}; configured query "
                f"embedder is {self._embedder.model_id!r} at dimension {self._embedder.dimension}"
            )
        if database_dimension != self._embedder.dimension:
            raise ValueError(
                f"PostgreSQL chunk.embedding uses Vector({database_dimension}); configured query "
                f"embedder dimension is {self._embedder.dimension}"
            )


def _validate_query_vector(vectors: list[list[float]], *, expected_dimension: int) -> list[float]:
    if len(vectors) != 1:
        raise ValueError(f"query embedder returned {len(vectors)} vectors for one query")
    vector = [float(value) for value in vectors[0]]
    if len(vector) != expected_dimension:
        raise ValueError(
            f"query embedder returned dimension {len(vector)}; expected {expected_dimension}"
        )
    if not all(isfinite(value) for value in vector):
        raise ValueError("query embedder returned a non-finite value")
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0 or abs(norm - 1.0) > 1e-3:
        raise ValueError("query embedder must return a unit-normalized vector")
    return vector


def _source_from_row(row: Mapping[Any, Any]) -> SourceDocument:
    metadata = SourceMetadata(
        bwb_id=str(row["bwb_id"]),
        regeling_titel=str(row["regeling_titel"]),
        artikel=str(row["artikel"]),
        lid=cast(str | None, row["lid"]),
        onderdeel=cast(str | None, row["onderdeel"]),
        opschrift=cast(str | None, row["opschrift"]),
        kop_pad=str(row["kop_pad"]),
        bron_url=str(row["bron_url"]),
        toestand_url=str(row["toestand_url"]),
        geldig_vanaf=cast(date, row["geldig_vanaf"]),
        geldig_tot=cast(date | None, row["geldig_tot"]),
        status=cast(LegalStatus, row["effective_status"]),
        artikel_status=cast(ArticleStatus, row["artikel_status"]),
    )
    return SourceDocument(
        chunk_id=cast(UUID, row["chunk_id"]),
        tekst=str(row["tekst"]),
        metadata=metadata,
    )


__all__ = ["PgHybridRetriever"]
