"""HTTP contract tests for date-aware search and source lookup."""

from __future__ import annotations

import asyncio
from datetime import date
from uuid import UUID

import httpx

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.db.engine import DbStatus
from wetvia.retrieval import ScoredChunk, SourceDocument, SourceMetadata
from wetvia.retrieval.testing import FakeRetriever

_CHUNK_ID = UUID("0b51c232-803b-5f94-a83c-8e12f3990029")
_PEILDATUM = date(2026, 10, 31)
_SYNTHETIC_URL = "https://example.test/source/synthetic-search-fixture"


def _source() -> SourceDocument:
    return SourceDocument(
        chunk_id=_CHUNK_ID,
        tekst="Synthetic search API fixture; not legal text.",
        metadata=SourceMetadata(
            bwb_id="TEST-SOURCE",
            regeling_titel="Synthetic API fixture (not a legal regulation)",
            artikel="test-article",
            lid=None,
            onderdeel="b",
            opschrift=None,
            kop_pad="Synthetic hierarchy",
            bron_url=_SYNTHETIC_URL,
            toestand_url=_SYNTHETIC_URL,
            geldig_vanaf=date(2026, 9, 24),
            geldig_tot=None,
            status="geldend",
            artikel_status="geldend",
        ),
    )


def _app(retriever: FakeRetriever | None = None):
    async def check_db() -> DbStatus:
        return "ok"

    context = HealthContext(llm_provider="ollama", version="0.0.0", check_db=check_db)
    return create_app(context, retriever=retriever)


def _request(app, method: str, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path)

    return asyncio.run(send())


def test_search_endpoint_serializes_source_metadata_and_forwards_options() -> None:
    source = _source()
    retriever = FakeRetriever([ScoredChunk(source=source, score=0.042)])

    response = _request(
        _app(retriever),
        "GET",
        "/api/search?q=hoogte%20dakkapel&peildatum=2026-10-31&k=3&include_future=true",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["source"]["metadata"]["artikel"] == "test-article"
    assert body["results"][0]["source"]["tekst"] == source.tekst
    assert body["results"][0]["score"] == 0.042
    assert retriever.search_calls == [("hoogte dakkapel", _PEILDATUM, 3, True, "hybrid")]


def test_source_endpoint_serializes_document_and_returns_404_for_unknown_id() -> None:
    source = _source()
    retriever = FakeRetriever(sources=[source])

    response = _request(_app(retriever), "GET", f"/api/sources/{_CHUNK_ID}")
    missing = _request(
        _app(retriever),
        "GET",
        "/api/sources/5a3d7c62-295b-5577-931a-8ab63df92bbf",
    )

    assert response.status_code == 200
    assert response.json()["chunk_id"] == str(_CHUNK_ID)
    assert response.json()["metadata"]["bron_url"] == source.metadata.bron_url
    assert response.json()["tekst"] == source.tekst
    assert missing.status_code == 404


def test_search_is_unavailable_when_no_retriever_was_injected() -> None:
    response = _request(
        _app(),
        "GET",
        "/api/search?q=hoogte&peildatum=2026-10-31",
    )

    assert response.status_code == 503
