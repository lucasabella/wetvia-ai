"""BWB-to-Postgres ingestion use cases."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import case, delete, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from nl_wetten_ingest import Chunk, Toestand, classify, parse_bwb_xml
from wetvia.db.schema import ChunkRecord, RegelingRecord, ToestandRecord

MVP_BWB_IDS = (
    "BWBR0037885",
    "BWBR0041278",
    "BWBR0041297",
    "BWBR0041330",
    "BWBR0045528",
    "BWBR0005537",
    "BWBR0005288",
)

EffectiveStatus = Literal["geldend", "toekomstig", "vervallen"]
ChunkParser = Callable[[bytes, Toestand], list[Chunk]]


class BwbSource(Protocol):
    """Public metadata and XML operations used by the ingestion service."""

    def search_toestanden(self, bwb_id: str) -> list[Toestand]: ...

    def changed_since(self, datum: date | str) -> list[Toestand]: ...

    def fetch_toestand_xml(self, toestand: Toestand) -> bytes: ...


@dataclass(frozen=True, slots=True)
class IngestReport:
    """Counts from one completed ingestion batch."""

    bwb_ids: tuple[str, ...]
    toestanden: int
    chunks: int


@dataclass(frozen=True, slots=True)
class _StoredState:
    modified: date
    has_chunks: bool


class IngestService:
    """Select official BWB states, parse them, and transactionally upsert them."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        source: BwbSource,
        *,
        parser: ChunkParser = parse_bwb_xml,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._sessions = session_factory
        self._source = source
        self._parser = parser
        self._today = today

    async def ingest_bwb(
        self,
        *,
        preset: str | None = None,
        ids: Sequence[str] | None = None,
        peildatum: date | None = None,
    ) -> IngestReport:
        """Ingest the MVP preset or explicitly selected BWB regulation IDs."""
        if (preset is None) == (ids is None):
            raise ValueError("specify exactly one of preset or ids")
        if preset is not None and preset != "mvp":
            raise ValueError(f"unknown BWB preset: {preset}")
        bwb_ids = MVP_BWB_IDS if preset == "mvp" else tuple(dict.fromkeys(ids or ()))
        if not bwb_ids:
            raise ValueError("at least one BWB-ID is required")

        effective_date = peildatum or self._today()
        regulation_reports: list[IngestReport] = []
        for bwb_id in bwb_ids:
            toestanden = await asyncio.to_thread(self._source.search_toestanden, bwb_id)
            if any(state.bwb_id != bwb_id for state in toestanden):
                raise ValueError(f"BWB history did not match requested ID {bwb_id}")
            regulation_reports.append(await self._ingest_history(toestanden, effective_date))
        return _combine_reports(regulation_reports)

    async def sync(self, *, peildatum: date | None = None) -> IngestReport:
        """Refresh changed MVP or tracked regulations and reclassify stored chunks."""
        effective_date = peildatum or self._today()
        changed = await asyncio.to_thread(
            self._source.changed_since,
            effective_date - timedelta(days=1),
        )
        tracked_ids, stored_history, existing_states = await self._load_tracked_history()

        syncable_ids = set(MVP_BWB_IDS) | set(tracked_ids)
        changed_ids = tuple(
            bwb_id
            for bwb_id in dict.fromkeys(state.bwb_id for state in changed)
            if bwb_id in syncable_ids
        )
        refresh_ids = tuple(dict.fromkeys((*tracked_ids, *changed_ids)))

        reports: list[IngestReport] = []
        for bwb_id in refresh_ids:
            # SRU changes require a complete source snapshot. Otherwise the
            # previously stored history is enough to reclassify states and
            # materialize a newly selected current/future document if missing.
            if bwb_id in changed_ids or not stored_history.get(bwb_id):
                history = await asyncio.to_thread(self._source.search_toestanden, bwb_id)
            else:
                history = stored_history[bwb_id]
            reports.append(
                await self._ingest_history(
                    history,
                    effective_date,
                    existing_states=existing_states.get(bwb_id),
                )
            )
        return _combine_reports(reports)

    async def _load_tracked_history(
        self,
    ) -> tuple[
        tuple[str, ...],
        dict[str, list[Toestand]],
        dict[str, dict[str, _StoredState]],
    ]:
        async with self._sessions() as session:
            tracked_ids = tuple(
                sorted(set((await session.scalars(select(RegelingRecord.bwb_id))).all()))
            )
            if not tracked_ids:
                return (), {}, {}

            state_rows = (
                await session.execute(
                    select(ToestandRecord, RegelingRecord.titel)
                    .join(RegelingRecord, RegelingRecord.bwb_id == ToestandRecord.bwb_id)
                    .where(ToestandRecord.bwb_id.in_(tracked_ids))
                )
            ).all()
            chunk_urls = set(
                (
                    await session.scalars(
                        select(ChunkRecord.toestand_url)
                        .where(ChunkRecord.bwb_id.in_(tracked_ids))
                        .distinct()
                    )
                ).all()
            )

        histories: dict[str, list[Toestand]] = {bwb_id: [] for bwb_id in tracked_ids}
        existing_states: dict[str, dict[str, _StoredState]] = {bwb_id: {} for bwb_id in tracked_ids}
        for record, titel in state_rows:
            state = Toestand(
                bwb_id=record.bwb_id,
                titel=titel,
                geldig_vanaf=record.geldig_vanaf,
                geldig_tot=record.geldig_tot,
                toestand_url=record.toestand_url,
                modified=record.modified,
            )
            histories[record.bwb_id].append(state)
            existing_states[record.bwb_id][record.toestand_url] = _StoredState(
                modified=record.modified,
                has_chunks=record.toestand_url in chunk_urls,
            )
        return (
            tracked_ids,
            {bwb_id: _unique_history(history) for bwb_id, history in histories.items()},
            existing_states,
        )

    async def _ingest_history(
        self,
        history: Sequence[Toestand],
        peildatum: date,
        *,
        existing_states: dict[str, _StoredState] | None = None,
    ) -> IngestReport:
        states = _unique_history(history)
        if not states:
            raise ValueError("no BWB Toestand metadata was returned")
        bwb_ids = {state.bwb_id for state in states}
        if len(bwb_ids) != 1:
            raise ValueError("a BWB history response contains multiple regulation IDs")
        bwb_id = next(iter(bwb_ids))

        selected = _select_current_and_next(states, peildatum)
        parsed: dict[str, tuple[Toestand, list[Chunk]]] = {}
        for state in selected:
            previous = (existing_states or {}).get(state.toestand_url)
            if previous is not None and previous.has_chunks and previous.modified == state.modified:
                continue
            xml_bytes = await asyncio.to_thread(self._source.fetch_toestand_xml, state)
            chunks = await asyncio.to_thread(self._parser, xml_bytes, state)
            parsed[state.toestand_url] = (state, chunks)

        title = next((state.titel for state in selected if state.titel), states[0].titel)
        async with self._sessions.begin() as session:
            await _upsert_regeling(session, bwb_id, title)
            await _upsert_history_metadata(session, states, peildatum)
            for state, chunks in parsed.values():
                await _upsert_chunks(session, state, chunks, peildatum)

        return IngestReport(
            bwb_ids=(bwb_id,),
            toestanden=len(selected),
            chunks=sum(len(chunks) for _, chunks in parsed.values()),
        )


def _unique_history(history: Sequence[Toestand]) -> list[Toestand]:
    states_by_url: dict[str, Toestand] = {}
    for state in history:
        existing = states_by_url.get(state.toestand_url)
        if existing is not None and existing != state:
            raise ValueError(f"conflicting metadata for Toestand URL {state.toestand_url}")
        states_by_url[state.toestand_url] = state
    return sorted(
        states_by_url.values(), key=lambda state: (state.geldig_vanaf, state.toestand_url)
    )


def _select_current_and_next(states: Sequence[Toestand], peildatum: date) -> list[Toestand]:
    current = [state for state in states if classify(state, peildatum) == "geldend"]
    if len(current) != 1:
        if not current:
            raise ValueError(f"no current BWB Toestand for {peildatum.isoformat()}")
        raise ValueError(f"multiple current BWB Toestanden for {peildatum.isoformat()}")

    future = [state for state in states if classify(state, peildatum) == "toekomstig"]
    selected = [current[0]]
    if future:
        selected.append(min(future, key=lambda state: (state.geldig_vanaf, state.toestand_url)))
    return selected


async def _upsert_regeling(session: AsyncSession, bwb_id: str, titel: str) -> None:
    statement = pg_insert(RegelingRecord).values(bwb_id=bwb_id, titel=titel)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[RegelingRecord.bwb_id],
            set_={"titel": statement.excluded.titel},
        )
    )


async def _upsert_history_metadata(
    session: AsyncSession,
    states: Sequence[Toestand],
    peildatum: date,
) -> None:
    values = [
        {
            "toestand_url": state.toestand_url,
            "bwb_id": state.bwb_id,
            "geldig_vanaf": state.geldig_vanaf,
            "geldig_tot": state.geldig_tot,
            "modified": state.modified,
        }
        for state in states
    ]
    statement = pg_insert(ToestandRecord).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[ToestandRecord.toestand_url],
            set_={
                "bwb_id": statement.excluded.bwb_id,
                "geldig_vanaf": statement.excluded.geldig_vanaf,
                "geldig_tot": statement.excluded.geldig_tot,
                "modified": statement.excluded.modified,
            },
        )
    )

    for state in states:
        effective_status = classify(state, peildatum)
        status_expression: ColumnElement[str]
        if effective_status == "toekomstig":
            status_expression = literal("toekomstig")
        elif effective_status == "vervallen":
            status_expression = literal("vervallen")
        else:
            status_expression = case(
                (ChunkRecord.artikel_status == "vervallen", "vervallen"),
                else_="geldend",
            )
        await session.execute(
            update(ChunkRecord)
            .where(ChunkRecord.toestand_url == state.toestand_url)
            .values(
                geldig_vanaf=state.geldig_vanaf,
                geldig_tot=state.geldig_tot,
                status=status_expression,
            )
        )

    history_urls = [state.toestand_url for state in states]
    await session.execute(
        delete(ToestandRecord).where(
            ToestandRecord.bwb_id == states[0].bwb_id,
            ToestandRecord.toestand_url.not_in(history_urls),
        )
    )


async def _upsert_chunks(
    session: AsyncSession,
    state: Toestand,
    chunks: Sequence[Chunk],
    peildatum: date,
) -> None:
    state_status = classify(state, peildatum)
    values = [
        {
            "id": uuid5(NAMESPACE_URL, f"{state.toestand_url}#{index}"),
            "toestand_url": state.toestand_url,
            "chunk_index": index,
            "bwb_id": chunk.bwb_id,
            "regeling_titel": chunk.regeling_titel,
            "artikel": chunk.artikel,
            "lid": chunk.lid,
            "onderdeel": chunk.onderdeel,
            "opschrift": chunk.opschrift,
            "kop_pad": chunk.kop_pad,
            "tekst": chunk.tekst,
            "geldig_vanaf": state.geldig_vanaf,
            "geldig_tot": state.geldig_tot,
            "bron_url": chunk.bron_url,
            "artikel_status": chunk.status,
            "status": _effective_status(chunk.status, state_status),
        }
        for index, chunk in enumerate(chunks)
    ]

    if values:
        statement = pg_insert(ChunkRecord).values(values)
        excluded = statement.excluded
        changed = or_(
            ChunkRecord.bwb_id.is_distinct_from(excluded.bwb_id),
            ChunkRecord.regeling_titel.is_distinct_from(excluded.regeling_titel),
            ChunkRecord.artikel.is_distinct_from(excluded.artikel),
            ChunkRecord.lid.is_distinct_from(excluded.lid),
            ChunkRecord.onderdeel.is_distinct_from(excluded.onderdeel),
            ChunkRecord.opschrift.is_distinct_from(excluded.opschrift),
            ChunkRecord.kop_pad.is_distinct_from(excluded.kop_pad),
            ChunkRecord.tekst.is_distinct_from(excluded.tekst),
            ChunkRecord.bron_url.is_distinct_from(excluded.bron_url),
            ChunkRecord.artikel_status.is_distinct_from(excluded.artikel_status),
        )
        update_values = {
            "bwb_id": excluded.bwb_id,
            "regeling_titel": excluded.regeling_titel,
            "artikel": excluded.artikel,
            "lid": excluded.lid,
            "onderdeel": excluded.onderdeel,
            "opschrift": excluded.opschrift,
            "kop_pad": excluded.kop_pad,
            "tekst": excluded.tekst,
            "geldig_vanaf": excluded.geldig_vanaf,
            "geldig_tot": excluded.geldig_tot,
            "bron_url": excluded.bron_url,
            "artikel_status": excluded.artikel_status,
            "status": excluded.status,
            "embedding": case((changed, None), else_=ChunkRecord.embedding),
        }
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[ChunkRecord.toestand_url, ChunkRecord.chunk_index],
                set_=update_values,
            )
        )

    indices = [value["chunk_index"] for value in values]
    stale_chunks = delete(ChunkRecord).where(ChunkRecord.toestand_url == state.toestand_url)
    if indices:
        stale_chunks = stale_chunks.where(ChunkRecord.chunk_index.not_in(indices))
    await session.execute(stale_chunks)


def _effective_status(article_status: str, state_status: EffectiveStatus) -> EffectiveStatus:
    if state_status == "toekomstig":
        return "toekomstig"
    if state_status == "vervallen" or article_status == "vervallen":
        return "vervallen"
    return "geldend"


def _combine_reports(reports: Sequence[IngestReport]) -> IngestReport:
    return IngestReport(
        bwb_ids=tuple(bwb_id for report in reports for bwb_id in report.bwb_ids),
        toestanden=sum(report.toestanden for report in reports),
        chunks=sum(report.chunks for report in reports),
    )
