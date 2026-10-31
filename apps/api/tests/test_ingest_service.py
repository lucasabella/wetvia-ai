"""Offline orchestration tests against official saved BWB SRU metadata."""

from __future__ import annotations

import re
from asyncio import run
from collections.abc import Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy.dialects.postgresql import dialect

from nl_wetten_ingest import BwbSRUClient, Toestand, parse_bwb_xml
from wetvia.ingest import MVP_BWB_IDS, IngestReport, IngestService

_ROOT = Path(__file__).resolve().parents[3]
_SRU_FIXTURES = _ROOT / "packages/nl-wetten-ingest/tests/fixtures"
_CURRENT_DATE = date(2026, 10, 31)


def _bbl_history() -> list[Toestand]:
    page_files = {"1": "bbl-page-1.xml", "6": "bbl-page-2.xml", "11": "bbl-page-3.xml"}

    def respond(request: httpx.Request) -> httpx.Response:
        page = page_files[request.url.params["startRecord"]]
        return httpx.Response(200, content=(_SRU_FIXTURES / page).read_bytes(), request=request)

    with BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client:
        return client.search_toestanden("BWBR0041297")


class _FakeSource:
    def __init__(
        self, history: Sequence[Toestand], *, payload: bytes = b"offline-test-input"
    ) -> None:
        self.history = list(history)
        self.payload = payload
        self.search_calls: list[str] = []
        self.changed_since_calls: list[date | str] = []
        self.fetch_calls: list[str] = []
        self.changed: list[Toestand] = []

    def search_toestanden(self, bwb_id: str) -> list[Toestand]:
        self.search_calls.append(bwb_id)
        return [state for state in self.history if state.bwb_id == bwb_id]

    def changed_since(self, datum: date | str) -> list[Toestand]:
        self.changed_since_calls.append(datum)
        return self.changed

    def fetch_toestand_xml(self, toestand: Toestand) -> bytes:
        self.fetch_calls.append(toestand.toestand_url)
        return self.payload


class _FakeSession:
    def __init__(
        self,
        *,
        fail_on: int | None = None,
        tracked_ids: set[str] | None = None,
    ) -> None:
        self.statements: list[object] = []
        self.fail_on = fail_on
        self.tracked_ids = tracked_ids or set()
        self.rolled_back = False

    async def scalars(self, statement: object) -> _FakeScalarResult:
        self.statements.append(statement)
        return _FakeScalarResult(self.tracked_ids)

    async def execute(self, statement: object) -> None:
        if self.fail_on is not None and len(self.statements) + 1 == self.fail_on:
            raise RuntimeError("simulated database write failure")
        self.statements.append(statement)


class _FakeScalarResult:
    def __init__(self, values: set[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        return list(self._values)


class _SessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, exc_type: object, *_: object) -> None:
        self._session.rolled_back = exc_type is not None
        return None


class _FakeSessionFactory:
    def __init__(self, *, fail_on: int | None = None, tracked_ids: set[str] | None = None) -> None:
        self.session = _FakeSession(fail_on=fail_on, tracked_ids=tracked_ids)

    def begin(self) -> _SessionContext:
        return _SessionContext(self.session)

    def __call__(self) -> _SessionContext:
        return _SessionContext(self.session)


def test_mvp_preset_matches_the_verified_seven_regulations() -> None:
    assert MVP_BWB_IDS == (
        "BWBR0037885",
        "BWBR0041278",
        "BWBR0041297",
        "BWBR0041330",
        "BWBR0045528",
        "BWBR0005537",
        "BWBR0005288",
    )


def test_ingest_rejects_missing_conflicting_and_unknown_selection_options() -> None:
    source = _FakeSource([])
    service = IngestService(
        _FakeSessionFactory(),  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
    )

    with pytest.raises(ValueError, match="specify exactly one"):
        run(service.ingest_bwb())
    with pytest.raises(ValueError, match="specify exactly one"):
        run(service.ingest_bwb(preset="mvp", ids=["BWBR0041297"]))
    with pytest.raises(ValueError, match="unknown BWB preset"):
        run(service.ingest_bwb(preset="unknown"))
    with pytest.raises(ValueError, match="at least one BWB-ID"):
        run(service.ingest_bwb(ids=[]))


def test_ingest_selects_current_and_nearest_future_official_states() -> None:
    history = _bbl_history()
    source = _FakeSource(history)
    sessions = _FakeSessionFactory()
    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
    )

    report = run(service.ingest_bwb(ids=["BWBR0041297"], peildatum=date(2026, 8, 1)))

    assert report == IngestReport(bwb_ids=("BWBR0041297",), toestanden=2, chunks=0)
    assert [
        state.geldig_vanaf for state in history if state.toestand_url in source.fetch_calls
    ] == [
        date(2026, 7, 1),
        date(2026, 9, 24),
    ]


def test_sync_uses_yesterday_then_reloads_complete_official_history() -> None:
    history = _bbl_history()
    source = _FakeSource(history)
    non_mvp = replace(history[-1], bwb_id="BWBR0000001")
    source.changed = [non_mvp, history[-1], history[-1]]
    sessions = _FakeSessionFactory()
    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
        today=lambda: _CURRENT_DATE,
    )

    report = run(service.sync())

    assert source.changed_since_calls == [date(2026, 10, 30)]
    assert source.search_calls == ["BWBR0041297"]
    assert source.fetch_calls == [history[-1].toestand_url]
    assert report == IngestReport(bwb_ids=("BWBR0041297",), toestanden=1, chunks=0)

    state_insert = next(
        statement
        for statement in sessions.session.statements
        if (
            getattr(statement, "__visit_name__", None) == "insert"
            and getattr(getattr(statement, "table", None), "name", None) == "toestand"
        )
    )
    state_insert_sql = state_insert.compile(dialect=dialect())  # type: ignore[attr-defined]
    stored_urls = [
        value
        for key, value in state_insert_sql.params.items()
        if "toestand_url" in key and isinstance(value, str)
    ]
    assert set(stored_urls) == {state.toestand_url for state in history}


def test_sync_refreshes_custom_regulations_that_were_previously_ingested() -> None:
    custom_id = "BWBR0000001"
    history = [replace(state, bwb_id=custom_id) for state in _bbl_history()]
    source = _FakeSource(history)
    source.changed = [history[-1]]
    sessions = _FakeSessionFactory(tracked_ids={custom_id})
    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
        today=lambda: _CURRENT_DATE,
    )

    report = run(service.sync())

    assert report.bwb_ids == (custom_id,)
    assert source.search_calls == [custom_id]
    assert source.fetch_calls == [history[-1].toestand_url]


def test_sync_reclassifies_tracked_statuses_when_changed_since_is_empty() -> None:
    custom_id = "BWBR0000001"
    source = _FakeSource([])
    sessions = _FakeSessionFactory(tracked_ids={custom_id})
    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
    )
    earlier_date = date(2026, 9, 23)
    later_date = date(2026, 9, 24)

    earlier_report = run(service.sync(peildatum=earlier_date))
    later_report = run(service.sync(peildatum=later_date))

    assert earlier_report == later_report == IngestReport(bwb_ids=(), toestanden=0, chunks=0)
    assert source.changed_since_calls == [date(2026, 9, 22), date(2026, 9, 23)]
    assert source.search_calls == []
    status_updates = [
        statement
        for statement in sessions.session.statements
        if (
            getattr(statement, "__visit_name__", None) == "update"
            and getattr(getattr(statement, "table", None), "name", None) == "chunk"
        )
    ]
    assert len(status_updates) == 2
    for statement, expected_date in zip(status_updates, [earlier_date, later_date], strict=True):
        params = statement.compile(dialect=dialect()).params
        assert expected_date in params.values()


def test_ingest_session_context_rolls_back_when_a_write_fails() -> None:
    history = _bbl_history()
    source = _FakeSource(history)
    sessions = _FakeSessionFactory(fail_on=2)
    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=lambda _xml, _state: [],
    )

    with pytest.raises(RuntimeError, match="simulated database write failure"):
        run(service.ingest_bwb(ids=["BWBR0041297"]))

    assert sessions.session.rolled_back


def test_chunk_upsert_uses_stable_ids_and_invalidates_embedding_on_content_change() -> None:
    history = _bbl_history()
    xml_path = _SRU_FIXTURES / "bwb_xml/bbl-2026-09-24.xml"
    payload = xml_path.read_bytes()
    source = _FakeSource(history, payload=payload)
    sessions = _FakeSessionFactory()

    parser_calls = 0

    def parser(xml_bytes: bytes, toestand: Toestand):
        nonlocal parser_calls
        parser_calls += 1
        max_chars = 4000 if parser_calls == 1 else 700
        return parse_bwb_xml(xml_bytes, toestand, max_chars=max_chars)

    service = IngestService(
        sessions,  # type: ignore[arg-type]
        source,
        parser=parser,
    )

    run(service.ingest_bwb(ids=["BWBR0041297"]))
    run(service.ingest_bwb(ids=["BWBR0041297"]))

    chunk_inserts = [
        statement
        for statement in sessions.session.statements
        if (
            getattr(statement, "__visit_name__", None) == "insert"
            and getattr(getattr(statement, "table", None), "name", None) == "chunk"
        )
    ]
    first_rows = chunk_inserts[0]._multi_values[0]
    second_rows = chunk_inserts[1]._multi_values[0]

    def value(row: dict[object, object], name: str) -> object:
        return next(value for column, value in row.items() if getattr(column, "name", None) == name)

    assert value(first_rows[9], "id") == value(second_rows[9], "id")
    assert value(first_rows[9], "tekst") != value(second_rows[9], "tekst")

    sql = str(chunk_inserts[1].compile(dialect=dialect()))
    assert "ON CONFLICT (toestand_url, chunk_index) DO UPDATE" in sql
    assert "IS DISTINCT FROM" in sql
    assert "embedding = CASE" in sql
    update_clause = sql.split("DO UPDATE SET", maxsplit=1)[1]
    assert re.search(r"(?:^|,)\s*id\s*=", update_clause) is None
