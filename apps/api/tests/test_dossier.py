"""Dossier composition, API, and source-boundary tests."""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

import wetvia.bootstrap as bootstrap
from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.api.openapi_export import build_openapi_spec
from wetvia.config import Settings
from wetvia.db.engine import DbStatus
from wetvia.dossier import (
    CHECKLIST_UNAVAILABLE_NOTE,
    CONCEPT_DISCLOSURE,
    ChecklistStatus,
    DakkapelDossierService,
    DossierFormat,
    DossierV1,
    ProjectomschrijvingV1,
)
from wetvia.dossier.service import _projectomschrijving
from wetvia.llm.adapters.fake import FakeProvider
from wetvia.rules import (
    DakkapelInvoer,
    Dakvlak,
    Gebiedsbescherming,
    Monumentrelatie,
    Oordeel,
    toets,
)


class CopyProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__([])

    async def chat(self, messages, schema, stream, temperature, **kwargs):
        self.calls.append((messages, schema, stream, temperature))
        return schema(projectomschrijving=messages[-1]["content"])


def _facts() -> DakkapelInvoer:
    return DakkapelInvoer(
        dakvlak=Dakvlak.ACHTER,
        dakvlak_naar_openbaar_toegankelijk_gebied=False,
        plat_dak=True,
        hoogte_m=Decimal("1.75"),
        onderzijde_boven_dakvoet_m=Decimal("0.75"),
        bovenzijde_onder_daknok_m=Decimal("0.75"),
        linker_zijkant_tot_dakvlakrand_m=Decimal("0.75"),
        rechter_zijkant_tot_dakvlakrand_m=Decimal("0.75"),
        monumentrelatie=Monumentrelatie.GEEN_MONUMENT,
        gebiedsbescherming=Gebiedsbescherming.GEEN,
    )


def _body(**updates: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "locatie": "Voorbeeldstraat 4",
        "invoer": {
            "dakvlak": "achterdakvlak",
            "dakvlak_naar_openbaar_toegankelijk_gebied": False,
            "plat_dak": True,
            "hoogte_m": "1.75",
            "onderzijde_boven_dakvoet_m": "0.75",
            "bovenzijde_onder_daknok_m": "0.75",
            "linker_zijkant_tot_dakvlakrand_m": "0.75",
            "rechter_zijkant_tot_dakvlakrand_m": "0.75",
            "monumentrelatie": "geen_monument",
            "gebiedsbescherming": "geen_rijksbeschermd_stads_of_dorpsgezicht",
        },
    }
    body.update(updates)
    return body


def test_dossier_schema_keeps_canonical_input_result_sources_and_empty_dso_state() -> None:
    async def create() -> DossierV1:
        service = DakkapelDossierService(
            CopyProvider(),
            today=lambda: date(2026, 11, 1),
        )
        return await service.create(_facts(), location="Voorbeeldstraat 4")

    dossier = asyncio.run(create())

    assert dossier.schema_version == "1.0"
    assert dossier.aanvrager.naam == "[Naam aanvrager invullen]"
    assert dossier.locatie == "Voorbeeldstraat 4"
    assert dossier.invoer == _facts()
    assert dossier.toetsing == toets(_facts())
    assert dossier.toetsing.eindoordeel is Oordeel.WAARSCHIJNLIJK_VERGUNNINGVRIJ
    assert {source.artikel for source in dossier.bronnen} == {
        "Bbl 2.27",
        "Bbl 2.29",
        "Bbl 2.30",
    }
    assert dossier.peildatum == date(2026, 11, 1)
    assert dossier.disclosure == CONCEPT_DISCLOSURE
    assert dossier.checklist.status is ChecklistStatus.NOT_RETRIEVED
    assert dossier.checklist.items == []
    assert dossier.checklist.toelichting == CHECKLIST_UNAVAILABLE_NOTE
    assert any("DSO-LV-lijst" in item for item in dossier.open_vragen)


def test_description_uses_only_canonical_facts() -> None:
    async def create(facts: DakkapelInvoer) -> DossierV1:
        return await DakkapelDossierService(CopyProvider()).create(
            facts, location="SECRET-PRIVATE-ADDRESS"
        )

    known = asyncio.run(create(replace(_facts(), hoogte_m=Decimal("1.2"))))
    unknown = asyncio.run(create(replace(_facts(), hoogte_m=None)))
    assert "Hoogte: 1.2 m" in known.projectomschrijving
    assert "2.5" not in known.projectomschrijving
    assert "Hoogte: onbekend" in unknown.projectomschrijving
    assert "1.75" not in unknown.projectomschrijving
    for dossier in (known, unknown):
        assert "Volgens de opgegeven gegevens" in dossier.projectomschrijving
        assert "SECRET-PRIVATE-ADDRESS" not in dossier.projectomschrijving
        assert "materiaal" not in dossier.projectomschrijving.lower()
        assert "vergunning" not in dossier.projectomschrijving.lower()
        assert len(dossier.projectomschrijving.split()) <= 120


def test_bootstrap_uses_local_provider_and_prompt_excludes_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Engine:
        async def dispose(self) -> None:
            return None

    local = CopyProvider()
    cloud = CopyProvider()
    monkeypatch.setattr(bootstrap, "create_db_engine", lambda _url: Engine())
    monkeypatch.setattr(bootstrap, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(bootstrap, "PgHybridRetriever", lambda *_args: object())
    monkeypatch.setattr(
        bootstrap, "get_chat_providers", lambda _settings: {"local": local, "cloud": cloud}
    )
    service = bootstrap.build_app(Settings(_env_file=None)).state.dossier_service
    assert service.description_provider is local
    asyncio.run(service.create(_facts(), location="SECRET-PRIVATE-ADDRESS"))
    assert "SECRET-PRIVATE-ADDRESS" not in str(local.calls[0][0])
    assert cloud.calls == []


@pytest.mark.parametrize(
    ("height", "old", "new"),
    [
        (Decimal("1.2"), "Hoogte: 1.2 m", "Hoogte: 2.5 m"),
        (None, "Hoogte: onbekend", "Hoogte: 1.75 m"),
        (None, "het achterdakvlak", "een zijdakvlak"),
        (None, "Plat dak: ja", "Plat dak: nee"),
        (None, "Hoogte: onbekend.", ""),
        (None, "Hoogte: onbekend.", "Hoogte: onbekend. Adres: Verzonnenstraat 1."),
        (None, "Hoogte: onbekend.", "Hoogte: onbekend. De dakkapel is van hout."),
        (None, "Hoogte: onbekend.", "Hoogte: onbekend. De vergunning is verleend."),
    ],
)
def test_model_deviations_fail_closed(height, old, new) -> None:
    facts = replace(_facts(), hoogte_m=height)
    canonical = _projectomschrijving(facts).projectomschrijving
    assert old in canonical
    response = json.dumps({"projectomschrijving": canonical.replace(old, new)})
    provider = FakeProvider([response])
    service = DakkapelDossierService(provider)
    with pytest.raises(ValueError, match="differs"):
        asyncio.run(service.create(facts, location="SECRET-PRIVATE-ADDRESS"))
    assert len(provider.calls) == 1


def test_model_deviation_returns_generic_502(caplog: pytest.LogCaptureFixture) -> None:
    canonical = _projectomschrijving(_facts()).projectomschrijving
    provider = FakeProvider([json.dumps({"projectomschrijving": canonical + " Verzonnenstraat."})])

    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(
        HealthContext(version="test", check_db=check_db),
        dossier_service=DakkapelDossierService(provider),
    )

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post("/api/dossier/dakkapel?format=md", json=_body())

    response = asyncio.run(send())
    assert response.status_code == 502
    assert response.json() == {"detail": "The concept dossier could not be generated."}
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.name == "wetvia.api.routes.dossier"
    assert record.getMessage() == "Concept dossier generation failed (exception_type=ValueError)"
    assert record.exc_info is None


def test_provider_failure_log_excludes_exception_and_location(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SENTINEL-PRIVATE-ADDRESS"

    class FailingProvider(CopyProvider):
        async def chat(self, messages, schema, stream, temperature, **kwargs):
            raise RuntimeError(f"provider returned private data: {sentinel}")

    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(
        HealthContext(version="test", check_db=check_db),
        dossier_service=DakkapelDossierService(FailingProvider()),
    )

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/dossier/dakkapel?format=md", json=_body(locatie=sentinel)
            )

    response = asyncio.run(send())
    assert response.status_code == 502
    assert response.json() == {"detail": "The concept dossier could not be generated."}
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.getMessage() == "Concept dossier generation failed (exception_type=RuntimeError)"
    assert record.exc_info is None
    assert sentinel not in caplog.text


def test_dossier_project_description_is_limited_to_120_words() -> None:
    with pytest.raises(ValueError, match="at most 120 words"):
        ProjectomschrijvingV1(projectomschrijving="woord " * 121)


def test_dossier_rendering_runs_off_the_async_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from wetvia.dossier.renderers import md

    event_loop_thread = threading.get_ident()
    render_thread: list[int] = []

    def render_in_thread(_dossier: DossierV1) -> str:
        render_thread.append(threading.get_ident())
        return "# CONCEPT"

    monkeypatch.setattr(md, "render_markdown", render_in_thread)

    async def create_attachment() -> bytes:
        service = DakkapelDossierService(CopyProvider())
        attachment = await service.create_attachment(
            _facts(),
            location="Voorbeeldstraat 4",
            format=DossierFormat.MARKDOWN,
        )
        return attachment.content

    assert asyncio.run(create_attachment()) == b"# CONCEPT"
    assert render_thread and render_thread[0] != event_loop_thread


def test_attachment_endpoint_returns_typed_download_and_rejects_client_results() -> None:
    service = DakkapelDossierService(CopyProvider(), today=lambda: date(2026, 11, 1))

    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(
        HealthContext(version="test", check_db=check_db),
        dossier_service=service,
    )
    transport = httpx.ASGITransport(app=app)

    async def send() -> tuple[
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
        httpx.Response,
    ]:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            markdown = await client.post(
                "/api/dossier/dakkapel?format=md",
                json=_body(),
            )
            docx = await client.post(
                "/api/dossier/dakkapel?format=docx",
                json=_body(),
            )
            pdf = await client.post(
                "/api/dossier/dakkapel?format=pdf",
                json=_body(),
            )
            invalid = await client.post(
                "/api/dossier/dakkapel?format=exe",
                json=_body(),
            )
            result_injection = await client.post(
                "/api/dossier/dakkapel?format=md",
                json=_body(toetsing={"eindoordeel": "waarschijnlijk_vergunningvrij"}),
            )
            return markdown, docx, pdf, invalid, result_injection

    response, docx_response, pdf_response, invalid_response, result_injection_response = (
        asyncio.run(send())
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="wetvia-dakkapel-concept.md"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    text = response.text
    assert "CONCEPT, gemaakt met Wetvia (AI). Niet gecontroleerd door een deskundige." in text
    assert "Voorbeeldstraat 4" in text
    assert "1.75 m" in text
    assert "officiële indieningsstukkenlijst" in text
    assert docx_response.status_code == 200
    assert docx_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert docx_response.headers["content-disposition"].endswith(
        'filename="wetvia-dakkapel-concept.docx"'
    )
    assert docx_response.content.startswith(b"PK")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.headers["content-disposition"].endswith(
        'filename="wetvia-dakkapel-concept.pdf"'
    )
    assert pdf_response.content.startswith(b"%PDF-")
    assert invalid_response.status_code == 422
    assert result_injection_response.status_code == 422


def test_attachment_endpoint_requires_dossier_service() -> None:
    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(HealthContext(version="test", check_db=check_db))
    transport = httpx.ASGITransport(app=app)

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/dossier/dakkapel?format=md", json=_body())

    response = asyncio.run(send())
    assert response.status_code == 503


def test_openapi_describes_attachment_formats_and_typed_input() -> None:
    schema = build_openapi_spec()
    operation = schema["paths"]["/api/dossier/dakkapel"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    response_content = operation["responses"]["200"]["content"]
    format_ref = operation["parameters"][0]["schema"]["$ref"]
    format_schema_name = format_ref.rsplit("/", maxsplit=1)[-1]
    format_schema = schema["components"]["schemas"][format_schema_name]

    assert request_ref.endswith("/DakkapelDossierRequest")
    assert operation["parameters"][0]["name"] == "format"
    assert set(format_schema["enum"]) == {"docx", "pdf", "md"}
    assert set(response_content) == {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/pdf",
        "text/markdown",
    }
    assert all(
        item["schema"] == {"type": "string", "format": "binary"}
        for item in response_content.values()
    )
