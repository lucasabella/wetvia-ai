"""Health endpoint and OpenAPI. The database check is injected, not a live server."""

import asyncio

import httpx
import pytest

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.db.engine import DbStatus


def _context(
    *,
    version: str = "0.0.0",
    db_status: DbStatus = "ok",
    cloud_configured: bool = False,
) -> HealthContext:
    async def check_db() -> DbStatus:
        return db_status

    return HealthContext(
        version=version,
        check_db=check_db,
        local_configured=True,
        cloud_configured=cloud_configured,
    )


def _get(
    path: str,
    *,
    version: str = "9.9.9",
    cloud_configured: bool = True,
) -> httpx.Response:
    app = create_app(_context(version=version, cloud_configured=cloud_configured))
    transport = httpx.ASGITransport(app=app)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_health_reports_injected_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_API_KEY", "should-not-leak")

    response = _get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "db": "ok",
        "configured_chat_modes": {"local": True, "cloud": True},
        "default_chat_mode": "local",
        "version": "9.9.9",
    }
    assert "should-not-leak" not in response.text


def test_health_degrades_when_database_check_fails() -> None:
    app = create_app(_context(db_status="error"))
    transport = httpx.ASGITransport(app=app)

    async def request() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/health")

    body = asyncio.run(request()).json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"


def test_openapi_is_served_under_api_docs() -> None:
    docs = _get("/api/docs")
    spec = _get("/api/openapi.json")

    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert spec.status_code == 200
    assert "/api/health" in spec.json()["paths"]
