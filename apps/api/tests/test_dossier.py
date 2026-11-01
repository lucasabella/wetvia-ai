"""Dossier composition, API, and source-boundary tests."""

from __future__ import annotations

import asyncio
import json
import threading
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
from wetvia.llm.adapters.fake import FakeProvider
from wetvia.rules import (
    DakkapelInvoer,
    Dakvlak,
    Gebiedsbescherming,
    Monumentrelatie,
    Oordeel,
    toets,
)


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


def _provider(description: str = "Plaatsen van een dakkapel aan de achterzijde.") -> FakeProvider:
    return FakeProvider([json.dumps({"projectomschrijving": description})])


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
            _provider(),
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


def test_local_description_prompt_excludes_address_and_cloud_provider() -> None:
    local = _provider()
    cloud = FakeProvider([])

    async def build_app_and_create() -> DossierV1:
        class Engine:
            async def dispose(self) -> None:
                return None

        engine = Engine()
        monkeypatch_values = {
            "create_db_engine": lambda _url: engine,
            "create_session_factory": lambda _engine: object(),
            "PgHybridRetriever": lambda *_args: object(),
            "get_chat_providers": lambda _settings: {"local": local, "cloud": cloud},
        }
        old_values = {name: getattr(bootstrap, name) for name in monkeypatch_values}
        try:
            for name, value in monkeypatch_values.items():
                setattr(bootstrap, name, value)
            app = bootstrap.build_app(Settings(_env_file=None))
            service: DakkapelDossierService = app.state.dossier_service
            assert service.description_provider is local
            return await service.create(_facts(), location="SECRET-PRIVATE-ADDRESS")
        finally:
            for name, value in old_values.items():
                setattr(bootstrap, name, value)

    dossier = asyncio.run(build_app_and_create())
    messages, schema, stream, temperature = local.calls[0]
    prompt = "\n".join(message["content"] for message in messages)
    assert schema is ProjectomschrijvingV1
    assert stream is False
    assert temperature == 0.2
    assert "SECRET-PRIVATE-ADDRESS" not in prompt
    assert dossier.locatie == "SECRET-PRIVATE-ADDRESS"
    assert cloud.calls == []


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
        service = DakkapelDossierService(_provider())
        attachment = await service.create_attachment(
            _facts(),
            location="Voorbeeldstraat 4",
            format=DossierFormat.MARKDOWN,
        )
        return attachment.content

    assert asyncio.run(create_attachment()) == b"# CONCEPT"
    assert render_thread and render_thread[0] != event_loop_thread


def test_attachment_endpoint_returns_typed_download_and_rejects_client_results() -> None:
    description = json.dumps({"projectomschrijving": "Plaatsen van een dakkapel."})
    provider = FakeProvider([description, description, description])
    service = DakkapelDossierService(provider, today=lambda: date(2026, 11, 1))

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
    assert "Voorbeeldstraat 4" not in provider.calls[0][0][1]["content"]


def test_attachment_endpoint_requires_local_dossier_service() -> None:
    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(HealthContext(version="test", check_db=check_db))
    transport = httpx.ASGITransport(app=app)

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/dossier/dakkapel?format=md", json=_body())

    response = asyncio.run(send())
    assert response.status_code == 503


def test_attachment_endpoint_hides_local_provider_failure() -> None:
    service = DakkapelDossierService(FakeProvider([]))

    async def check_db() -> DbStatus:
        return "ok"

    app = create_app(
        HealthContext(version="test", check_db=check_db),
        dossier_service=service,
    )
    transport = httpx.ASGITransport(app=app)

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/dossier/dakkapel?format=md", json=_body())

    response = asyncio.run(send())
    assert response.status_code == 502
    assert response.json() == {"detail": "The concept dossier could not be generated."}


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
