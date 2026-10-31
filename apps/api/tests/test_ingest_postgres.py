"""PostgreSQL schema and end-to-end ingest coverage for CI's isolated database."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from nl_wetten_ingest import BwbSRUClient, Chunk, Toestand, classify, parse_bwb_xml
from wetvia.db import create_db_engine, create_session_factory
from wetvia.db.schema import ChunkRecord, RegelingRecord, ToestandRecord
from wetvia.ingest import IngestService

_API_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_ROOT.parents[1]
_FIXTURE_ROOT = _REPO_ROOT / "packages/nl-wetten-ingest/tests/fixtures"
_BWB_ID = "BWBR0041297"
_PEILDATUM = date(2026, 10, 31)


class _OfficialFixtureSource:
    def __init__(self, history: list[Toestand], xml: bytes) -> None:
        self.history = history
        self.xml = xml
        self.current = next(state for state in history if classify(state, _PEILDATUM) == "geldend")
        self.changed = [self.current]
        self.search_calls: list[str] = []
        self.fetch_calls: list[str] = []

    def search_toestanden(self, bwb_id: str) -> list[Toestand]:
        assert bwb_id == _BWB_ID
        self.search_calls.append(bwb_id)
        return list(self.history)

    def changed_since(self, datum: date | str) -> list[Toestand]:
        return list(self.changed)

    def fetch_toestand_xml(self, toestand: Toestand) -> bytes:
        assert toestand.bwb_id == _BWB_ID
        self.fetch_calls.append(toestand.toestand_url)
        return self.xml


def _official_history() -> list[Toestand]:
    pages = {"1": "bbl-page-1.xml", "6": "bbl-page-2.xml", "11": "bbl-page-3.xml"}

    def respond(request: httpx.Request) -> httpx.Response:
        page = pages[request.url.params["startRecord"]]
        return httpx.Response(
            200,
            content=(_FIXTURE_ROOT / page).read_bytes(),
            request=request,
        )

    with BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client:
        return client.search_toestanden(_BWB_ID)


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


def test_postgres_migration_and_ingest_upserts_real_official_fixture(
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
    history = _official_history()
    xml = (_FIXTURE_ROOT / "bwb_xml/bbl-2026-09-24.xml").read_bytes()
    source = _OfficialFixtureSource(history, xml)
    engine = create_db_engine(database_url)
    sessions = create_session_factory(engine)

    async def exercise() -> None:
        try:
            # This test owns only the MVP fixture's rows in the dedicated CI database.
            async with sessions.begin() as session:
                await session.execute(
                    delete(RegelingRecord).where(RegelingRecord.bwb_id == _BWB_ID)
                )

            async with engine.connect() as connection:
                extension = await connection.scalar(
                    text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                )
                assert extension == "vector"
                generated_tsv = await connection.scalar(
                    text(
                        "SELECT is_generated FROM information_schema.columns "
                        "WHERE table_schema = current_schema() "
                        "AND table_name = 'chunk' AND column_name = 'tsv'"
                    )
                )
                assert generated_tsv == "ALWAYS"
                vector_type = await connection.scalar(
                    text(
                        "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                        "WHERE attrelid = 'chunk'::regclass AND attname = 'embedding'"
                    )
                )
                assert vector_type == "vector(1024)"
                indexes = set(
                    (
                        await connection.execute(
                            text(
                                "SELECT indexname FROM pg_indexes "
                                "WHERE schemaname = current_schema() AND tablename = 'chunk'"
                            )
                        )
                    ).scalars()
                )
                assert {
                    "ix_chunk_tsv_gin",
                    "ix_chunk_embedding_hnsw",
                    "ix_chunk_validity",
                } <= indexes

            default_service = IngestService(sessions, source)
            report = await default_service.ingest_bwb(ids=[_BWB_ID], peildatum=_PEILDATUM)
            assert report.bwb_ids == (_BWB_ID,)
            assert report.toestanden == 1
            assert report.chunks > 0

            async with sessions() as session:
                regulation = await session.get(RegelingRecord, _BWB_ID)
                assert regulation is not None
                assert regulation.titel == "Besluit bouwwerken leefomgeving"
                assert await session.scalar(
                    select(func.count())
                    .select_from(ToestandRecord)
                    .where(ToestandRecord.bwb_id == _BWB_ID)
                ) == len(history)
                original_count = await session.scalar(
                    select(func.count())
                    .select_from(ChunkRecord)
                    .where(ChunkRecord.bwb_id == _BWB_ID)
                )
                assert original_count == report.chunks
                chunk = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.chunk_index == 9,
                    )
                )
                assert chunk is not None
                stable_id = chunk.id
                original_text = chunk.tekst
                assert chunk.tsv is not None
                assert chunk.embedding is None

            # A repeated import is an upsert: it keeps chunk identity and row count.
            repeated = await default_service.ingest_bwb(ids=[_BWB_ID], peildatum=_PEILDATUM)
            assert repeated.chunks == report.chunks
            async with sessions() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ChunkRecord)
                        .where(ChunkRecord.bwb_id == _BWB_ID)
                    )
                    == original_count
                )
                chunk = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.chunk_index == 9,
                    )
                )
                assert chunk is not None and chunk.id == stable_id

            async with sessions.begin() as session:
                await session.execute(
                    update(ChunkRecord)
                    .where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.chunk_index == 9,
                    )
                    .values(embedding=[0.125] * 1024)
                )

            # Identical legal content keeps the already computed vector.
            await default_service.ingest_bwb(ids=[_BWB_ID], peildatum=_PEILDATUM)
            async with sessions() as session:
                unchanged_chunk = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.chunk_index == 9,
                    )
                )
                assert unchanged_chunk is not None and unchanged_chunk.embedding is not None
                assert float(unchanged_chunk.embedding[0]) == pytest.approx(0.125)

            predecessor = max(
                (state for state in history if state.geldig_vanaf < source.current.geldig_vanaf),
                key=lambda state: state.geldig_vanaf,
            )
            async with sessions.begin() as session:
                await session.execute(
                    update(ToestandRecord)
                    .where(ToestandRecord.toestand_url == predecessor.toestand_url)
                    .values(geldig_tot=None)
                )

            def smaller_chunks(xml_bytes: bytes, toestand: Toestand) -> list[Chunk]:
                return parse_bwb_xml(xml_bytes, toestand, max_chars=700)

            changed_current = replace(
                source.current,
                modified=source.current.modified + timedelta(days=1),
            )
            source.history = [
                changed_current if state.toestand_url == source.current.toestand_url else state
                for state in history
            ]
            source.changed = [changed_current]
            changed_service = IngestService(sessions, source, parser=smaller_chunks)
            sync_report = await changed_service.sync(peildatum=_PEILDATUM)
            assert sync_report.bwb_ids == (_BWB_ID,)
            assert source.current.toestand_url
            async with sessions() as session:
                changed_chunk = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.chunk_index == 9,
                    )
                )
                assert changed_chunk is not None
                assert changed_chunk.id == stable_id
                assert changed_chunk.tekst != original_text
                assert changed_chunk.embedding is None
                repaired_predecessor = await session.get(ToestandRecord, predecessor.toestand_url)
                assert repaired_predecessor is not None
                assert repaired_predecessor.geldig_tot == source.current.geldig_vanaf - timedelta(
                    days=1
                )

            # A failed chunk write must roll back metadata and regulation updates too.
            changed_history = [replace(state, titel="Uncommitted title") for state in history]
            failing_source = _OfficialFixtureSource(changed_history, xml)

            def invalid_chunk(xml_bytes: bytes, toestand: Toestand) -> list[Chunk]:
                chunks = parse_bwb_xml(xml_bytes, toestand, max_chars=700)
                return [replace(chunks[0], status=cast(Any, "invalid")), *chunks[1:]]

            failing_service = IngestService(sessions, failing_source, parser=invalid_chunk)
            with pytest.raises(IntegrityError):
                await failing_service.ingest_bwb(ids=[_BWB_ID], peildatum=_PEILDATUM)
            async with sessions() as session:
                regulation = await session.get(RegelingRecord, _BWB_ID)
                assert regulation is not None
                assert regulation.titel == "Besluit bouwwerken leefomgeving"
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(ChunkRecord)
                        .where(ChunkRecord.bwb_id == _BWB_ID)
                    )
                    == sync_report.chunks
                )

            # Date passage alone moves the stored future state to geldend and
            # its predecessor to vervallen, even if SRU reports no changes.
            async with sessions.begin() as session:
                await session.execute(
                    update(ChunkRecord)
                    .where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.artikel_status == "geldend",
                    )
                    .values(status="toekomstig")
                )
                session.add(
                    ChunkRecord(
                        id=uuid5(NAMESPACE_URL, f"{predecessor.toestand_url}#status-test"),
                        toestand_url=predecessor.toestand_url,
                        chunk_index=0,
                        bwb_id=_BWB_ID,
                        regeling_titel="Synthetic status test row",
                        artikel="status-test",
                        lid=None,
                        onderdeel=None,
                        opschrift=None,
                        kop_pad="Synthetic status test row",
                        tekst="Synthetic status transition assertion; not legal text.",
                        geldig_vanaf=predecessor.geldig_vanaf,
                        geldig_tot=predecessor.geldig_tot,
                        bron_url=predecessor.toestand_url,
                        artikel_status="geldend",
                        status="geldend",
                    )
                )

            searches_before_status_sync = len(source.search_calls)
            fetches_before_status_sync = len(source.fetch_calls)
            source.changed = []
            status_sync = await IngestService(sessions, source).sync(
                peildatum=source.current.geldig_vanaf
            )
            assert status_sync.bwb_ids == (_BWB_ID,)
            assert status_sync.toestanden == 1
            assert status_sync.chunks == 0
            assert len(source.search_calls) == searches_before_status_sync
            assert len(source.fetch_calls) == fetches_before_status_sync
            async with sessions() as session:
                previous_status = await session.scalar(
                    select(ChunkRecord.status).where(
                        ChunkRecord.toestand_url == predecessor.toestand_url,
                        ChunkRecord.chunk_index == 0,
                    )
                )
                current_status = await session.scalar(
                    select(ChunkRecord.status)
                    .where(
                        ChunkRecord.toestand_url == source.current.toestand_url,
                        ChunkRecord.artikel_status == "geldend",
                    )
                    .limit(1)
                )
                assert previous_status == "vervallen"
                assert current_status == "geldend"
            assert source.search_calls[-1] == _BWB_ID
            assert source.changed == []

            # Start with official history where one future state follows the
            # current state. At its start date, sync must materialize the next
            # future state from stored metadata without re-fetching unchanged XML.
            initial_date = date(2026, 2, 1)
            initial_current = next(
                state for state in history if classify(state, initial_date) == "geldend"
            )
            initial_future = min(
                (state for state in history if classify(state, initial_date) == "toekomstig"),
                key=lambda state: state.geldig_vanaf,
            )
            transition_date = initial_future.geldig_vanaf
            next_future = min(
                (state for state in history if classify(state, transition_date) == "toekomstig"),
                key=lambda state: state.geldig_vanaf,
            )

            def synthetic_chunk(_xml_bytes: bytes, state: Toestand) -> list[Chunk]:
                return [
                    Chunk(
                        bwb_id=state.bwb_id,
                        regeling_titel="Synthetic status transition fixture",
                        artikel="sync-test",
                        lid=None,
                        onderdeel=None,
                        opschrift=None,
                        kop_pad="Synthetic test data",
                        tekst="Synthetic transition regression row; not legal text.",
                        geldig_vanaf=state.geldig_vanaf,
                        geldig_tot=state.geldig_tot,
                        bron_url=state.toestand_url,
                        toestand_url=state.toestand_url,
                        status="geldend",
                    )
                ]

            transition_service = IngestService(sessions, source, parser=synthetic_chunk)
            initial_transition_report = await transition_service.ingest_bwb(
                ids=[_BWB_ID],
                peildatum=initial_date,
            )
            assert initial_transition_report.toestanden == 2
            assert source.fetch_calls[-2:] == [
                initial_current.toestand_url,
                initial_future.toestand_url,
            ]

            source.changed = []
            searches_before_transition_sync = len(source.search_calls)
            fetches_before_transition_sync = len(source.fetch_calls)
            transition_report = await transition_service.sync(peildatum=transition_date)
            assert transition_report.bwb_ids == (_BWB_ID,)
            assert transition_report.toestanden == 2
            assert transition_report.chunks == 1
            assert len(source.search_calls) == searches_before_transition_sync
            assert source.fetch_calls[fetches_before_transition_sync:] == [next_future.toestand_url]

            async with sessions() as session:
                for state in (initial_current, initial_future, next_future):
                    row = await session.scalar(
                        select(ChunkRecord).where(
                            ChunkRecord.toestand_url == state.toestand_url,
                            ChunkRecord.chunk_index == 0,
                        )
                    )
                    assert row is not None
                previous_row = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == initial_current.toestand_url,
                        ChunkRecord.chunk_index == 0,
                    )
                )
                current_row = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == initial_future.toestand_url,
                        ChunkRecord.chunk_index == 0,
                    )
                )
                next_row = await session.scalar(
                    select(ChunkRecord).where(
                        ChunkRecord.toestand_url == next_future.toestand_url,
                        ChunkRecord.chunk_index == 0,
                    )
                )
                assert previous_row is not None and previous_row.status == "vervallen"
                assert current_row is not None and current_row.status == "geldend"
                assert next_row is not None and next_row.status == "toekomstig"
        finally:
            await engine.dispose()

    asyncio.run(exercise())
