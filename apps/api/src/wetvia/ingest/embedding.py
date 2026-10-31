"""Bounded, resumable embedding writes for chunks with a NULL vector."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from wetvia.db.schema import ChunkRecord, EmbeddingConfigRecord
from wetvia.embeddings import Embedder, format_document_input

_DEFAULT_BATCH_SIZE = 32
_DEFAULT_MAX_BATCHES = 100


@dataclass(frozen=True, slots=True)
class EmbeddingReport:
    """Work completed by one bounded pass through NULL embedding rows."""

    batches: int
    embedded: int
    skipped_stale: int
    batch_limit_reached: bool


@dataclass(frozen=True, slots=True)
class _PendingChunk:
    id: UUID
    regeling_titel: str
    kop_pad: str
    artikel: str
    opschrift: str | None
    tekst: str

    def input_text(self) -> str:
        return format_document_input(
            self.regeling_titel,
            self.kop_pad,
            self.artikel,
            self.opschrift,
            self.tekst,
        )


class EmbeddingJob:
    """Embed NULL-only chunks in bounded batches and resume on the next run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
    ) -> None:
        if not embedder.model_id.strip():
            raise ValueError("embedding model ID must not be empty")
        if len(embedder.model_id) > 512:
            raise ValueError("embedding model ID must be at most 512 characters")
        if batch_size <= 0:
            raise ValueError("embedding batch size must be positive")
        if embedder.dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        self._sessions = session_factory
        self._embedder = embedder
        self._model_id = embedder.model_id
        self._batch_size = batch_size

    async def run(
        self,
        *,
        max_batches: int = _DEFAULT_MAX_BATCHES,
        batch_size: int | None = None,
    ) -> EmbeddingReport:
        """Process at most ``max_batches`` batches, committing each atomically."""
        size = self._batch_size if batch_size is None else batch_size
        if size <= 0:
            raise ValueError("embedding batch size must be positive")
        if max_batches <= 0:
            raise ValueError("maximum embedding batches must be positive")

        await self._ensure_model_identity()
        batches = 0
        embedded = 0
        skipped_stale = 0
        while batches < max_batches:
            pending = await self._load_pending(size)
            if not pending:
                break

            vectors = await asyncio.to_thread(
                self._embedder.embed,
                [chunk.input_text() for chunk in pending],
            )
            _validate_vectors(vectors, len(pending), self._embedder.dimension)
            saved, skipped = await self._save_batch(pending, vectors)
            batches += 1
            embedded += saved
            skipped_stale += skipped

        batch_limit_reached = batches == max_batches and await self._has_pending()

        return EmbeddingReport(
            batches=batches,
            embedded=embedded,
            skipped_stale=skipped_stale,
            batch_limit_reached=batch_limit_reached,
        )

    async def _load_pending(self, limit: int) -> list[_PendingChunk]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(
                        ChunkRecord.id,
                        ChunkRecord.regeling_titel,
                        ChunkRecord.kop_pad,
                        ChunkRecord.artikel,
                        ChunkRecord.opschrift,
                        ChunkRecord.tekst,
                    )
                    .where(ChunkRecord.embedding.is_(None))
                    .order_by(ChunkRecord.id)
                    .limit(limit)
                )
            ).all()
        return [_PendingChunk(*row) for row in rows]

    async def _has_pending(self) -> bool:
        async with self._sessions() as session:
            pending_count = await session.scalar(
                select(func.count()).select_from(ChunkRecord).where(ChunkRecord.embedding.is_(None))
            )
        return bool(pending_count)

    async def _ensure_model_identity(self) -> None:
        async with self._sessions.begin() as session:
            database_dimension = await _read_database_dimension(session)
            if database_dimension != self._embedder.dimension:
                raise ValueError(
                    f"configured embedding dimension {self._embedder.dimension} does not match "
                    f"PostgreSQL chunk.embedding Vector({database_dimension}); migrate the "
                    "column and vector index before running the new model"
                )
            stored = await session.scalar(
                select(EmbeddingConfigRecord).where(EmbeddingConfigRecord.id == 1).with_for_update()
            )
            if stored is None:
                existing_vectors = await session.scalar(
                    select(func.count())
                    .select_from(ChunkRecord)
                    .where(ChunkRecord.embedding.is_not(None))
                )
                if existing_vectors:
                    raise ValueError(
                        "stored vectors have no recorded model identity; clear and re-embed "
                        "them before running this job"
                    )
                statement = pg_insert(EmbeddingConfigRecord).values(
                    id=1,
                    model_id=self._model_id,
                    dimension=self._embedder.dimension,
                )
                await session.execute(
                    statement.on_conflict_do_nothing(index_elements=[EmbeddingConfigRecord.id])
                )
                stored = await session.scalar(
                    select(EmbeddingConfigRecord)
                    .where(EmbeddingConfigRecord.id == 1)
                    .with_for_update()
                )
                if stored is None:
                    raise RuntimeError("embedding model identity could not be initialized")

            if stored.model_id != self._model_id or stored.dimension != self._embedder.dimension:
                existing_vectors = await session.scalar(
                    select(func.count())
                    .select_from(ChunkRecord)
                    .where(ChunkRecord.embedding.is_not(None))
                )
                if existing_vectors:
                    raise ValueError(
                        f"stored vectors use {stored.model_id!r} at dimension "
                        f"{stored.dimension}; clear and re-embed all vectors before using "
                        f"{self._model_id!r} at dimension {self._embedder.dimension}"
                    )
                await session.execute(
                    update(EmbeddingConfigRecord)
                    .where(EmbeddingConfigRecord.id == 1)
                    .values(model_id=self._model_id, dimension=self._embedder.dimension)
                )

    async def _save_batch(
        self,
        pending: Sequence[_PendingChunk],
        vectors: Sequence[Sequence[float]],
    ) -> tuple[int, int]:
        saved = 0
        skipped = 0
        async with self._sessions.begin() as session:
            stored = await session.scalar(
                select(EmbeddingConfigRecord).where(EmbeddingConfigRecord.id == 1).with_for_update()
            )
            if (
                stored is None
                or stored.model_id != self._model_id
                or stored.dimension != self._embedder.dimension
            ):
                raise RuntimeError("embedding model identity changed while a batch was running")
            for chunk, vector in zip(pending, vectors, strict=True):
                unchanged_input = and_(
                    ChunkRecord.regeling_titel.is_not_distinct_from(chunk.regeling_titel),
                    ChunkRecord.kop_pad.is_not_distinct_from(chunk.kop_pad),
                    ChunkRecord.artikel.is_not_distinct_from(chunk.artikel),
                    ChunkRecord.opschrift.is_not_distinct_from(chunk.opschrift),
                    ChunkRecord.tekst.is_not_distinct_from(chunk.tekst),
                )
                result = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(ChunkRecord)
                        .where(
                            ChunkRecord.id == chunk.id,
                            ChunkRecord.embedding.is_(None),
                            unchanged_input,
                        )
                        .values(embedding=list(vector))
                    ),
                )
                if result.rowcount == 1:
                    saved += 1
                elif result.rowcount == 0:
                    skipped += 1
                else:
                    raise RuntimeError("embedding update affected an unexpected number of rows")
        return saved, skipped


async def _read_database_dimension(session: AsyncSession) -> int:
    type_name = await session.scalar(
        text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'chunk'::regclass AND attname = 'embedding'"
        )
    )
    match = re.fullmatch(r"vector\((\d+)\)", type_name or "")
    if match is None:
        raise RuntimeError("chunk.embedding must use a fixed-dimension PostgreSQL vector type")
    return int(match.group(1))


def _validate_vectors(
    vectors: Sequence[Sequence[float]], expected_count: int, expected_dimension: int
) -> None:
    if len(vectors) != expected_count:
        raise ValueError(f"embedder returned {len(vectors)} vectors for {expected_count} chunks")
    for vector in vectors:
        if len(vector) != expected_dimension:
            raise ValueError(
                f"embedder returned a {len(vector)}-dimension vector; "
                f"database requires {expected_dimension}"
            )
        values = [float(value) for value in vector]
        if not all(isfinite(value) for value in values):
            raise ValueError("embedder returned a vector containing a non-finite value")
        norm = sqrt(sum(value * value for value in values))
        if norm == 0 or abs(norm - 1.0) > 1e-3:
            raise ValueError("embedder must return unit-normalized vectors")
