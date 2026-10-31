"""PostgreSQL integration tests against the saved official Bbl XML fixture."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import threading
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url

from nl_wetten_ingest import Chunk, Toestand, parse_bwb_xml
from wetvia.db import create_db_engine, create_session_factory
from wetvia.db.schema import ChunkRecord, EmbeddingConfigRecord, RegelingRecord, ToestandRecord
from wetvia.embeddings import format_document_input
from wetvia.retrieval.adapters.pg import PgHybridRetriever
from wetvia.retrieval.hybrid import QUERY_INSTRUCTION
from wetvia.retrieval.rrf import ARTICLE_MATCH_BOOST, reciprocal_rank_score

_API_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_ROOT.parents[1]
_FIXTURE_DIR = _REPO_ROOT / "packages/nl-wetten-ingest/tests/fixtures/bwb_xml"
_BWB_ID = "BWBR0041297"
_SYNTHETIC_BWB_ID = "TEST-RETRIEVAL"
_STATE_URL = (
    "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/"
    "2026-09-24_0/xml/BWBR0041297_2026-09-24_0.xml"
)
_PEILDATUM = date(2026, 10, 31)
_MODEL_ID = "fixture/dutch-legal-token-hash"
_DIMENSION = 1024


class _FixtureEmbedder:
    model_id = _MODEL_ID
    dimension = _DIMENSION

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.thread_ids: list[int] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        self.thread_ids.append(threading.get_ident())
        return [_vector_for(text) for text in texts]


def _vector_for(text: str) -> list[float]:
    query = text.startswith("Instruct:")
    source = text.split("Query:", maxsplit=1)[1] if query else text
    terms = {_normalize_token(token) for token in re.findall(r"[a-z0-9]+", source.lower())}
    if query and source.strip() == "rrfcheck":
        return _basis_vector(2)
    if not query and "rrfcheck" in terms:
        return _basis_vector(2)
    if query and source.strip() == "2.29":
        return _basis_vector(0)
    if query and source.strip() == "Synthetic regulation Alpha 2.29 alphaonlyneedle":
        return _basis_vector(3)
    if query and {"hoog", "dakkapel", "vergunningvrij"} <= terms:
        return _basis_vector(1)
    if (
        not query
        and re.search(r"\bArtikel 2\.29(?:\s|\()", source, re.IGNORECASE)
        and "dakkapel" in terms
    ):
        # Offline stand-in for semantic similarity on the official Bbl fixture.
        return _basis_vector(1)
    vector = [0.0] * _DIMENSION
    for token in terms:
        slot = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "big")
        vector[slot % _DIMENSION] += 1.0
    vector[-1] += 0.01
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else [1.0] + [0.0] * (_DIMENSION - 1)


def _basis_vector(index: int) -> list[float]:
    vector = [0.0] * _DIMENSION
    vector[index] = 1.0
    return vector


def _normalize_token(token: str) -> str:
    if token.startswith("hoog"):
        return "hoog"
    if token.startswith("dakkapel"):
        return "dakkapel"
    if token.startswith("vergunningvrij"):
        return "vergunningvrij"
    return token


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


def _official_chunks() -> tuple[Toestand, list[Chunk]]:
    toestand = Toestand(
        bwb_id=_BWB_ID,
        titel="Besluit bouwwerken leefomgeving",
        geldig_vanaf=date(2026, 9, 24),
        geldig_tot=None,
        toestand_url=_STATE_URL,
        modified=date(2026, 9, 30),
    )
    xml = (_FIXTURE_DIR / "bbl-2026-09-24.xml").read_bytes()
    return toestand, parse_bwb_xml(xml, toestand)


def _record(chunk: Chunk, chunk_index: int) -> ChunkRecord:
    document_input = format_document_input(
        chunk.regeling_titel,
        chunk.kop_pad,
        chunk.artikel,
        chunk.opschrift,
        chunk.tekst,
    )
    return ChunkRecord(
        id=uuid5(NAMESPACE_URL, f"{chunk.toestand_url}#{chunk_index}"),
        toestand_url=chunk.toestand_url,
        chunk_index=chunk_index,
        bwb_id=chunk.bwb_id,
        regeling_titel=chunk.regeling_titel,
        artikel=chunk.artikel,
        lid=chunk.lid,
        onderdeel=chunk.onderdeel,
        opschrift=chunk.opschrift,
        kop_pad=chunk.kop_pad,
        tekst=chunk.tekst,
        geldig_vanaf=chunk.geldig_vanaf,
        geldig_tot=chunk.geldig_tot,
        bron_url=chunk.bron_url,
        artikel_status=chunk.status,
        # Deliberately stale for live articles: retrieval must calculate status
        # against the requested peildatum instead of trusting this field.
        status="vervallen" if chunk.status == "vervallen" else "toekomstig",
        embedding=_vector_for(document_input),
    )


def _synthetic_record(
    *,
    article: str,
    text: str,
    state_url: str,
    valid_from: date,
    valid_until: date | None,
    article_status: str = "geldend",
    status: str = "geldend",
    embedding: list[float] | None = None,
    bwb_id: str = _SYNTHETIC_BWB_ID,
    regulation_title: str = "Synthetic retrieval test (not legal text)",
) -> ChunkRecord:
    document_input = format_document_input(
        regulation_title,
        "Synthetic fixture metadata",
        article,
        None,
        text,
    )
    chunk_id = uuid5(NAMESPACE_URL, f"{state_url}#{article}")
    return ChunkRecord(
        id=chunk_id,
        toestand_url=state_url,
        chunk_index=0,
        bwb_id=bwb_id,
        regeling_titel=regulation_title,
        artikel=article,
        lid=None,
        onderdeel=None,
        opschrift=None,
        kop_pad="Synthetic fixture metadata",
        tekst=text,
        geldig_vanaf=valid_from,
        geldig_tot=valid_until,
        bron_url=state_url,
        artikel_status=article_status,
        status=status,
        embedding=embedding if embedding is not None else _vector_for(document_input),
    )


def test_pg_hybrid_search_uses_official_bbl_fixture_and_date_filters(
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
    toestand, official_chunks = _official_chunks()
    embedder = _FixtureEmbedder()
    engine = create_db_engine(database_url)
    sessions = create_session_factory(engine)
    future_url = "https://example.test/toestand/future"
    boundary_url = "https://example.test/toestand/boundary"
    expired_url = "https://example.test/toestand/expired"
    repealed_url = "https://example.test/toestand/repealed"
    rrf_url = "https://example.test/toestand/rrf"
    fts_only_url = "https://example.test/toestand/fts-only"
    collision_1229_url = "https://example.test/toestand/collision-12-29"
    collision_2290_url = "https://example.test/toestand/collision-2-290"
    alpha_url = "https://example.test/toestand/synthetic-alpha"
    beta_url = "https://example.test/toestand/synthetic-beta"
    alpha_bwb_id = "TEST-ALPHA"
    beta_bwb_id = "TEST-BETA"
    future_id = uuid5(NAMESPACE_URL, f"{future_url}#future-test")
    boundary_id = uuid5(NAMESPACE_URL, f"{boundary_url}#boundary-test")
    expired_id = uuid5(NAMESPACE_URL, f"{expired_url}#expired-test")
    repealed_id = uuid5(NAMESPACE_URL, f"{repealed_url}#repealed-test")
    rrf_id = uuid5(NAMESPACE_URL, f"{rrf_url}#rrf-test")
    fts_only_id = uuid5(NAMESPACE_URL, f"{fts_only_url}#fts-only")
    collision_1229_id = uuid5(NAMESPACE_URL, f"{collision_1229_url}#12.29")
    collision_2290_id = uuid5(NAMESPACE_URL, f"{collision_2290_url}#2.290")
    alpha_id = uuid5(NAMESPACE_URL, f"{alpha_url}#2.29")
    beta_id = uuid5(NAMESPACE_URL, f"{beta_url}#2.29")
    synthetic_text = "Synthetic dakkapel hoogte vergunningvrij marker; not legal text."
    fts_only_record = _synthetic_record(
        article="fts-only",
        text="nullvectorneedle; synthetic retrieval fixture, not legal text.",
        state_url=fts_only_url,
        valid_from=date(2020, 1, 1),
        valid_until=None,
    )
    fts_only_record.embedding = None

    async def exercise() -> None:
        try:
            async with sessions.begin() as session:
                await session.execute(
                    delete(RegelingRecord).where(RegelingRecord.bwb_id == _BWB_ID)
                )
                session.add(RegelingRecord(bwb_id=_BWB_ID, titel=toestand.titel))
                session.add(
                    RegelingRecord(
                        bwb_id=_SYNTHETIC_BWB_ID,
                        titel="Synthetic retrieval test (not a legal regulation)",
                    )
                )
                session.add_all(
                    [
                        RegelingRecord(
                            bwb_id=alpha_bwb_id,
                            titel="Synthetic regulation Alpha (not legal text)",
                        ),
                        RegelingRecord(
                            bwb_id=beta_bwb_id,
                            titel="Synthetic regulation Beta (not legal text)",
                        ),
                    ]
                )
                session.add(
                    ToestandRecord(
                        toestand_url=toestand.toestand_url,
                        bwb_id=_BWB_ID,
                        geldig_vanaf=toestand.geldig_vanaf,
                        geldig_tot=toestand.geldig_tot,
                        modified=toestand.modified,
                    )
                )
                synthetic_states = [
                    (future_url, date(2027, 1, 1), None),
                    (boundary_url, date(2020, 1, 1), _PEILDATUM),
                    (expired_url, date(2020, 1, 1), date(2026, 10, 30)),
                    (repealed_url, date(2020, 1, 1), None),
                    (rrf_url, date(2020, 1, 1), None),
                    (fts_only_url, date(2020, 1, 1), None),
                    (collision_1229_url, date(2020, 1, 1), None),
                    (collision_2290_url, date(2020, 1, 1), None),
                ]
                session.add_all(
                    [
                        ToestandRecord(
                            toestand_url=state_url,
                            bwb_id=_SYNTHETIC_BWB_ID,
                            geldig_vanaf=valid_from,
                            geldig_tot=valid_until,
                            modified=valid_from,
                        )
                        for state_url, valid_from, valid_until in synthetic_states
                    ]
                )
                session.add_all(
                    [
                        ToestandRecord(
                            toestand_url=alpha_url,
                            bwb_id=alpha_bwb_id,
                            geldig_vanaf=date(2020, 1, 1),
                            geldig_tot=None,
                            modified=date(2020, 1, 1),
                        ),
                        ToestandRecord(
                            toestand_url=beta_url,
                            bwb_id=beta_bwb_id,
                            geldig_vanaf=date(2020, 1, 1),
                            geldig_tot=None,
                            modified=date(2020, 1, 1),
                        ),
                    ]
                )
                await session.flush()
                session.add(EmbeddingConfigRecord(id=1, model_id=_MODEL_ID, dimension=_DIMENSION))
                session.add_all(
                    [_record(chunk, index) for index, chunk in enumerate(official_chunks)]
                )
                session.add_all(
                    [
                        _synthetic_record(
                            article="future-test",
                            text=synthetic_text,
                            state_url=future_url,
                            valid_from=date(2027, 1, 1),
                            valid_until=None,
                            status="geldend",
                        ),
                        _synthetic_record(
                            article="boundary-test",
                            text="Synthetic boundary marker; not legal text.",
                            state_url=boundary_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=_PEILDATUM,
                            status="toekomstig",
                        ),
                        _synthetic_record(
                            article="expired-test",
                            text=synthetic_text,
                            state_url=expired_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=date(2026, 10, 30),
                        ),
                        _synthetic_record(
                            article="repealed-test",
                            text=synthetic_text,
                            state_url=repealed_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                            article_status="vervallen",
                        ),
                        _synthetic_record(
                            article="rrf-test",
                            text=(
                                "rrfcheck unique marker; synthetic retrieval fixture, "
                                "not legal text."
                            ),
                            state_url=rrf_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                        ),
                        fts_only_record,
                        _synthetic_record(
                            article="12.29",
                            text="Synthetic article label collision fixture; not legal text.",
                            state_url=collision_1229_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                            embedding=_basis_vector(0),
                        ),
                        _synthetic_record(
                            article="2.290",
                            text="Synthetic article label collision fixture; not legal text.",
                            state_url=collision_2290_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                            embedding=_basis_vector(0),
                        ),
                        _synthetic_record(
                            article="2.29",
                            text="alphaonlyneedle; synthetic Alpha record, not legal text.",
                            state_url=alpha_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                            embedding=_basis_vector(3),
                            bwb_id=alpha_bwb_id,
                            regulation_title="Synthetic regulation Alpha (not legal text)",
                        ),
                        _synthetic_record(
                            article="2.29",
                            text="unrelatedbeta; synthetic Beta record, not legal text.",
                            state_url=beta_url,
                            valid_from=date(2020, 1, 1),
                            valid_until=None,
                            embedding=[-value for value in _basis_vector(3)],
                            bwb_id=beta_bwb_id,
                            regulation_title="Synthetic regulation Beta (not legal text)",
                        ),
                    ]
                )

            retriever = PgHybridRetriever(sessions, embedder)
            fts_only_embedder = _FixtureEmbedder()
            fts_only_embedder.model_id = "fixture/not-the-stored-space"
            fts_retriever = PgHybridRetriever(sessions, fts_only_embedder)
            fts_only_results = await fts_retriever.search(
                "nullvectorneedle",
                _PEILDATUM,
                k=8,
                mode="fts",
            )
            assert fts_only_results[0].source.chunk_id == fts_only_id
            assert fts_only_embedder.calls == []

            vector_only_results = await retriever.search(
                "nullvectorneedle",
                _PEILDATUM,
                k=60,
                mode="vector",
            )
            assert fts_only_id not in {result.source.chunk_id for result in vector_only_results}

            results = await retriever.search(
                "hoogte dakkapel vergunningvrij",
                _PEILDATUM,
                k=8,
            )
            ranks = [
                (
                    index,
                    result.source.metadata.artikel,
                    result.source.metadata.onderdeel,
                    result.score,
                )
                for index, result in enumerate(results, start=1)
            ]
            assert any(result.source.metadata.artikel == "2.29" for result in results[:3]), ranks[
                :15
            ]
            result_229 = next(
                result for result in results if result.source.metadata.artikel == "2.29"
            )
            assert result_229.source.metadata.status == "geldend"
            assert result_229.source.metadata.bron_url.startswith("https://wetten.overheid.nl/")
            assert embedder.calls[-1] == [
                f"Instruct: {QUERY_INSTRUCTION}\nQuery: hoogte dakkapel vergunningvrij"
            ]
            assert embedder.thread_ids[-1] != threading.get_ident()

            article_reference_results = await retriever.search("2.29", _PEILDATUM, k=60)
            assert article_reference_results
            article_results_by_id = {
                result.source.chunk_id: result for result in article_reference_results
            }
            assert any(
                result.source.metadata.bwb_id == _BWB_ID
                and result.source.metadata.artikel == "2.29"
                for result in article_reference_results
            )
            assert {collision_1229_id, collision_2290_id} <= set(article_results_by_id)
            largest_unboosted_rrf = 2 * reciprocal_rank_score(1)
            assert article_results_by_id[collision_1229_id].score <= largest_unboosted_rrf
            assert article_results_by_id[collision_2290_id].score <= largest_unboosted_rrf

            qualified_query = "Synthetic regulation Alpha 2.29 alphaonlyneedle"
            qualified_fts = await retriever.search(
                qualified_query,
                _PEILDATUM,
                k=60,
                mode="fts",
            )
            qualified_vector = await retriever.search(
                qualified_query,
                _PEILDATUM,
                k=60,
                mode="vector",
            )
            qualified_results = await retriever.search(qualified_query, _PEILDATUM, k=60)
            alpha_fts_result = next(
                result for result in qualified_fts if result.source.chunk_id == alpha_id
            )
            alpha_vector_result = next(
                result for result in qualified_vector if result.source.chunk_id == alpha_id
            )
            qualified_ids = {result.source.chunk_id for result in qualified_results}
            assert alpha_id in qualified_ids
            assert beta_id not in qualified_ids
            async with sessions() as session:
                fts_score = (
                    await session.execute(
                        text(
                            "SELECT ts_rank_cd(tsv, websearch_to_tsquery('dutch', :query)) "
                            "FROM chunk WHERE id = :chunk_id"
                        ),
                        {"query": qualified_query, "chunk_id": alpha_id},
                    )
                ).scalar_one()
                vector_score = (
                    await session.execute(
                        text(
                            "SELECT 1.0 - (embedding <=> CAST(:query_vector AS vector)) "
                            "FROM chunk WHERE id = :chunk_id"
                        ),
                        {
                            "query_vector": str(_basis_vector(3)),
                            "chunk_id": alpha_id,
                        },
                    )
                ).scalar_one()
            assert alpha_fts_result.score == pytest.approx(fts_score)
            assert alpha_vector_result.score == pytest.approx(vector_score)
            alpha_result = next(
                result for result in qualified_results if result.source.chunk_id == alpha_id
            )
            assert alpha_result.score == pytest.approx(
                2 * reciprocal_rank_score(1) + ARTICLE_MATCH_BOOST
            )

            rrf_results = await retriever.search("rrfcheck", _PEILDATUM, k=60)
            rrf_result = next(result for result in rrf_results if result.source.chunk_id == rrf_id)
            assert rrf_result.score == pytest.approx(2 * reciprocal_rank_score(1))

            fts_only_results = await retriever.search("nullvectorneedle", _PEILDATUM, k=60)
            fts_only_result = next(
                result for result in fts_only_results if result.source.chunk_id == fts_only_id
            )
            assert fts_only_result.score == pytest.approx(reciprocal_rank_score(1))

            wrong_model = _FixtureEmbedder()
            wrong_model.model_id = "fixture/other-vector-space"
            with pytest.raises(ValueError, match="stored vectors use"):
                await PgHybridRetriever(sessions, wrong_model).search("dakkapel", _PEILDATUM)
            assert wrong_model.calls == []
            wrong_dimension = _FixtureEmbedder()
            wrong_dimension.dimension = _DIMENSION - 1
            with pytest.raises(ValueError, match="configured query embedder"):
                await PgHybridRetriever(sessions, wrong_dimension).search("dakkapel", _PEILDATUM)
            assert wrong_dimension.calls == []

            future_excluded = await retriever.search("future marker", _PEILDATUM, k=60)
            assert future_id not in {result.source.chunk_id for result in future_excluded}

            future_included = await retriever.search(
                "future marker", _PEILDATUM, k=60, include_future=True
            )
            future_result = next(
                result for result in future_included if result.source.chunk_id == future_id
            )
            assert future_result.source.metadata.status == "toekomstig"
            assert expired_id not in {result.source.chunk_id for result in future_included}
            assert repealed_id not in {result.source.chunk_id for result in future_included}

            start_boundary = await retriever.search("future marker", date(2027, 1, 1), k=60)
            future_on_start = next(
                result for result in start_boundary if result.source.chunk_id == future_id
            )
            assert future_on_start.source.metadata.status == "geldend"

            end_boundary = await retriever.search("boundary marker", _PEILDATUM, k=60)
            boundary_result = next(
                result for result in end_boundary if result.source.chunk_id == boundary_id
            )
            assert boundary_result.source.metadata.status == "geldend"
            after_end = await retriever.search("boundary marker", date(2026, 11, 1), k=60)
            assert boundary_id not in {result.source.chunk_id for result in after_end}

            source = await retriever.get_source(result_229.source.chunk_id, peildatum=_PEILDATUM)
            assert source == result_229.source
            assert await retriever.get_source(uuid5(NAMESPACE_URL, "missing")) is None
            assert len(official_chunks) > 100
        finally:
            await engine.dispose()

    asyncio.run(exercise())
