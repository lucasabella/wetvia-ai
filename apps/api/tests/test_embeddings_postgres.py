"""PostgreSQL integration coverage for bounded embedding job semantics."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from datetime import date
from math import sqrt
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from wetvia.db import create_db_engine, create_session_factory
from wetvia.db.schema import ChunkRecord, EmbeddingConfigRecord, RegelingRecord, ToestandRecord
from wetvia.embeddings import format_document_input
from wetvia.ingest import EmbeddingJob

_API_ROOT = Path(__file__).resolve().parents[1]
_BWB_ID = "BWBR9999999"
_MODEL_ID = "stub/multilingual-e5"
_TOESTAND_URL = "https://example.test/toestand/embedding-job"
_UNIT_VECTOR = [1 / sqrt(1024)] * 1024


class _StubEmbedder:
    dimension = 1024
    model_id = "stub/multilingual-e5"

    def __init__(
        self,
        *,
        fail: bool = False,
        vector: list[float] | None = None,
        model_id: str = _MODEL_ID,
        dimension: int = 1024,
    ) -> None:
        self.fail = fail
        self.vector = vector or _UNIT_VECTOR
        self.model_id = model_id
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def embed(self, inputs: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(inputs))
        if self.fail:
            raise RuntimeError("stub inference failure")
        return [self.vector.copy() for _ in inputs]


def _chunk(index: int, *, article: str | None = None, chunk_id: UUID | None = None) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id or uuid5(NAMESPACE_URL, f"embedding-job-test#{index}"),
        toestand_url=_TOESTAND_URL,
        chunk_index=index,
        bwb_id=_BWB_ID,
        regeling_titel="Synthetic embedding test regulation",
        artikel=article or f"test-{index}",
        lid=None,
        onderdeel=None,
        opschrift=f"Synthetic heading {index}",
        kop_pad="Synthetic test hierarchy",
        tekst=f"Synthetic text {index}; not legal text.",
        geldig_vanaf=date(2026, 1, 1),
        geldig_tot=None,
        bron_url=_TOESTAND_URL,
        artikel_status="geldend",
        status="geldend",
    )


def _upgrade_schema(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config(str(_API_ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(_API_ROOT / "src" / "wetvia" / "db" / "alembic"),
    )
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_embedding_job_is_bounded_resumable_atomic_and_stale_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ.get("WETVIA_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("WETVIA_TEST_DATABASE_URL is set by the PostgreSQL CI job")
    url = make_url(database_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.database != "wetvia_test"
        or url.host not in {"localhost", "127.0.0.1"}
    ):
        pytest.fail("WETVIA_TEST_DATABASE_URL must point to the dedicated wetvia_test database")

    _upgrade_schema(database_url, monkeypatch)
    engine = create_db_engine(database_url)
    sessions = create_session_factory(engine)

    async def exercise() -> None:
        try:
            async with sessions.begin() as session:
                session.add(
                    RegelingRecord(bwb_id=_BWB_ID, titel="Synthetic embedding test regulation")
                )
                await session.flush()
                session.add(
                    ToestandRecord(
                        toestand_url=_TOESTAND_URL,
                        bwb_id=_BWB_ID,
                        geldig_vanaf=date(2026, 1, 1),
                        geldig_tot=None,
                        modified=date(2026, 1, 1),
                    )
                )
                await session.flush()
                session.add_all([_chunk(index) for index in range(5)])

            embedder = _StubEmbedder()
            job = EmbeddingJob(sessions, embedder, batch_size=2)
            first = await job.run(max_batches=1)
            assert first.batches == 1
            assert first.embedded == 2
            assert first.batch_limit_reached
            assert len(embedder.calls) == 1
            assert all("Synthetic test hierarchy" in value for value in embedder.calls[0])

            prefilled_embedding = [0.0] * 1023 + [1.0]
            async with sessions.begin() as session:
                prefilled_id = await session.scalar(
                    select(ChunkRecord.id)
                    .where(ChunkRecord.bwb_id == _BWB_ID, ChunkRecord.embedding.is_(None))
                    .order_by(ChunkRecord.id)
                    .limit(1)
                )
                assert prefilled_id is not None
                await session.execute(
                    update(ChunkRecord)
                    .where(ChunkRecord.id == prefilled_id)
                    .values(embedding=prefilled_embedding)
                )

            resumed = await job.run(max_batches=1)
            assert resumed.batches == 1
            assert resumed.embedded == 2
            assert not resumed.batch_limit_reached
            assert len(embedder.calls) == 2

            empty = await job.run(max_batches=1)
            assert empty.batches == 0
            assert not empty.batch_limit_reached
            async with sessions() as session:
                config = await session.get(EmbeddingConfigRecord, 1)
                assert config is not None
                assert config.model_id == _MODEL_ID
                assert config.dimension == 1024
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ChunkRecord)
                        .where(
                            ChunkRecord.bwb_id == _BWB_ID,
                            ChunkRecord.embedding.is_(None),
                        )
                    )
                    == 0
                )
                assert (
                    await session.scalar(
                        select(ChunkRecord.embedding).where(ChunkRecord.id == prefilled_id)
                    )
                    == prefilled_embedding
                )
                formatted_text = await session.scalar(
                    select(ChunkRecord.tekst).where(ChunkRecord.chunk_index == 0)
                )
                assert formatted_text == "Synthetic text 0; not legal text."
                assert format_document_input(
                    "Synthetic embedding test regulation",
                    "Synthetic test hierarchy",
                    "test-0",
                    "Synthetic heading 0",
                    formatted_text,
                ) in {input_text for batch in embedder.calls for input_text in batch}

            with pytest.raises(ValueError, match="stored vectors use"):
                await EmbeddingJob(
                    sessions,
                    _StubEmbedder(model_id="stub/other-model"),
                ).run(max_batches=1)
            with pytest.raises(ValueError, match=r"PostgreSQL chunk\.embedding Vector\(1024\)"):
                await EmbeddingJob(
                    sessions,
                    _StubEmbedder(dimension=3, model_id="stub/three-dimension"),
                ).run(max_batches=1)

            async with sessions.begin() as session:
                session.add(_chunk(5))
            failed_job = EmbeddingJob(
                sessions,
                _StubEmbedder(fail=True),
                batch_size=1,
            )
            with pytest.raises(RuntimeError, match="stub inference failure"):
                await failed_job.run(max_batches=1)
            with pytest.raises(ValueError, match="database requires 1024"):
                await EmbeddingJob(
                    sessions,
                    _StubEmbedder(vector=[1.0, 0.0, 0.0]),
                    batch_size=1,
                ).run(max_batches=1)
            async with sessions() as session:
                assert (
                    await session.scalar(
                        select(ChunkRecord.embedding).where(ChunkRecord.chunk_index == 5)
                    )
                    is None
                )

            # The two updates below share one transaction. The trigger makes the
            # second update fail so the first write must also roll back.
            await EmbeddingJob(sessions, _StubEmbedder()).run(max_batches=1)
            atomic_ids = sorted(
                [
                    uuid5(NAMESPACE_URL, "embedding-job-atomic-a"),
                    uuid5(NAMESPACE_URL, "embedding-job-atomic-b"),
                ]
            )
            async with sessions.begin() as session:
                session.add_all(
                    [
                        _chunk(6, article="trigger-ok", chunk_id=atomic_ids[0]),
                        _chunk(7, article="trigger-failure", chunk_id=atomic_ids[1]),
                    ]
                )
            async with engine.begin() as connection:
                await connection.execute(
                    text("DROP FUNCTION IF EXISTS wetvia_test_reject_embedding() CASCADE")
                )
                await connection.execute(
                    text(
                        "CREATE FUNCTION wetvia_test_reject_embedding() RETURNS trigger "
                        "LANGUAGE plpgsql AS $$ BEGIN "
                        "IF NEW.artikel = 'trigger-failure' THEN "
                        "RAISE EXCEPTION 'injected embedding write failure'; END IF; "
                        "RETURN NEW; END; $$"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE TRIGGER wetvia_test_reject_embedding BEFORE UPDATE OF embedding "
                        "ON chunk FOR EACH ROW EXECUTE FUNCTION wetvia_test_reject_embedding()"
                    )
                )
            with pytest.raises(DBAPIError, match="injected embedding write failure"):
                await EmbeddingJob(
                    sessions,
                    _StubEmbedder(),
                    batch_size=2,
                ).run(max_batches=1)
            async with sessions() as session:
                values = (
                    await session.scalars(
                        select(ChunkRecord.embedding)
                        .where(ChunkRecord.id.in_(atomic_ids))
                        .order_by(ChunkRecord.id)
                    )
                ).all()
                assert values == [None, None]
            async with engine.begin() as connection:
                await connection.execute(text("DROP TRIGGER wetvia_test_reject_embedding ON chunk"))
                await connection.execute(text("DROP FUNCTION wetvia_test_reject_embedding()"))
            await EmbeddingJob(sessions, _StubEmbedder()).run(max_batches=1)

            # Mutate one input after the SELECT and during inference. Conditional
            # updates must skip the stale vector; the next run uses new text.
            stale_id = uuid5(NAMESPACE_URL, "embedding-job-stale-row")
            async with sessions.begin() as session:
                session.add(_chunk(8, chunk_id=stale_id))

            loop = asyncio.get_running_loop()

            async def change_input() -> None:
                async with sessions.begin() as session:
                    await session.execute(
                        update(ChunkRecord)
                        .where(ChunkRecord.id == stale_id)
                        .values(tekst="Synthetic corrected text; not legal text.")
                    )

            class _MutatingEmbedder:
                dimension = 1024
                model_id = _MODEL_ID

                def __init__(self) -> None:
                    self.inputs: list[str] = []

                def embed(self, inputs: Sequence[str]) -> list[list[float]]:
                    self.inputs = list(inputs)
                    future = asyncio.run_coroutine_threadsafe(change_input(), loop)
                    future.result(timeout=10)
                    return [_UNIT_VECTOR.copy() for _ in inputs]

            mutating = _MutatingEmbedder()
            stale_report = await EmbeddingJob(
                sessions,
                mutating,
                batch_size=1,  # type: ignore[arg-type]
            ).run(max_batches=1)
            assert stale_report.embedded == 0
            assert stale_report.skipped_stale == 1
            assert len(mutating.inputs) == 1
            assert "Synthetic text 8" in mutating.inputs[0]
            async with sessions() as session:
                stale_row = await session.get(ChunkRecord, stale_id)
                assert stale_row is not None
                assert stale_row.embedding is None
                assert stale_row.tekst == "Synthetic corrected text; not legal text."

            final_embedder = _StubEmbedder()
            final_report = await EmbeddingJob(sessions, final_embedder).run(max_batches=1)
            assert final_report.embedded == 1
            assert "Synthetic corrected text" in final_embedder.calls[0][0]

            # Competing first-time model choices must settle on one space; a
            # losing worker may not write after the singleton identity changes.
            async with sessions.begin() as session:
                await session.execute(
                    update(ChunkRecord).where(ChunkRecord.bwb_id == _BWB_ID).values(embedding=None)
                )
                await session.execute(
                    delete(EmbeddingConfigRecord).where(EmbeddingConfigRecord.id == 1)
                )
            first_model = "stub/concurrent-a"
            second_model = "stub/concurrent-b"
            first_vector = _UNIT_VECTOR.copy()
            second_vector = [-value for value in _UNIT_VECTOR]
            outcomes = await asyncio.gather(
                EmbeddingJob(
                    sessions,
                    _StubEmbedder(vector=first_vector, model_id=first_model),
                    batch_size=32,
                ).run(max_batches=1),
                EmbeddingJob(
                    sessions,
                    _StubEmbedder(vector=second_vector, model_id=second_model),
                    batch_size=32,
                ).run(max_batches=1),
                return_exceptions=True,
            )
            assert sum(isinstance(outcome, Exception) for outcome in outcomes) == 1
            async with sessions() as session:
                active_config = await session.get(EmbeddingConfigRecord, 1)
                assert active_config is not None
                active_vectors = (
                    await session.scalars(
                        select(ChunkRecord.embedding)
                        .where(ChunkRecord.bwb_id == _BWB_ID)
                        .order_by(ChunkRecord.id)
                    )
                ).all()
                assert all(vector is not None for vector in active_vectors)
                sign = 1 if active_config.model_id == first_model else -1
                assert all(vector is not None and vector[0] * sign > 0 for vector in active_vectors)

            # A follow-up schema migration can change the column/index and
            # setting; the runtime job supports the new configured width.
            async with sessions.begin() as session:
                await session.execute(
                    update(ChunkRecord).where(ChunkRecord.bwb_id == _BWB_ID).values(embedding=None)
                )
                await session.execute(
                    delete(EmbeddingConfigRecord).where(EmbeddingConfigRecord.id == 1)
                )
            async with engine.begin() as connection:
                await connection.execute(text("DROP INDEX ix_chunk_embedding_hnsw"))
                await connection.execute(
                    text(
                        "ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(3) "
                        "USING NULL::vector(3)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw "
                        "(embedding vector_cosine_ops)"
                    )
                )
            three_dim_report = await EmbeddingJob(
                sessions,
                _StubEmbedder(
                    model_id="stub/three-dimension",
                    dimension=3,
                    vector=[1.0, 0.0, 0.0],
                ),
            ).run(max_batches=1, batch_size=32)
            assert three_dim_report.embedded == len(active_vectors)
            async with sessions() as session:
                three_dim_config = await session.get(EmbeddingConfigRecord, 1)
                assert three_dim_config is not None
                assert three_dim_config.dimension == 3
                three_dim = await session.scalar(
                    text(
                        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                        "WHERE attrelid = 'chunk'::regclass AND attname = 'embedding'"
                    )
                )
                assert three_dim == "vector(3)"
        finally:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DROP TRIGGER IF EXISTS wetvia_test_reject_embedding ON chunk")
                )
                await connection.execute(
                    text("DROP FUNCTION IF EXISTS wetvia_test_reject_embedding() CASCADE")
                )
            async with sessions.begin() as session:
                await session.execute(delete(EmbeddingConfigRecord))
                await session.execute(
                    delete(RegelingRecord).where(RegelingRecord.bwb_id == _BWB_ID)
                )
            async with engine.begin() as connection:
                await connection.execute(text("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw"))
                await connection.execute(
                    text(
                        "ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(1024) "
                        "USING NULL::vector(1024)"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX ix_chunk_embedding_hnsw ON chunk USING hnsw "
                        "(embedding vector_cosine_ops)"
                    )
                )
            await engine.dispose()

    asyncio.run(exercise())
