"""HTTP contract and strict decimal input tests for the dakkapel check."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx
import pytest

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.api.openapi_export import build_openapi_spec
from wetvia.api.schemas.rules import DakkapelRuleResponse
from wetvia.db.engine import DbStatus
from wetvia.rules import DakkapelInvoer, Dakvlak, Gebiedsbescherming, Monumentrelatie, toets


def _body(**updates: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
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
    }
    body.update(updates)
    return body


def _app():
    async def check_db() -> DbStatus:
        return "ok"

    return create_app(HealthContext(version="0.0.0", check_db=check_db))


def _post(body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app())

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            return await client.post("/api/rules/dakkapel", json=body)

    return asyncio.run(send())


def test_endpoint_maps_canonical_decimal_strings_to_public_rule_check() -> None:
    body = _body()
    response = _post(body)

    assert response.status_code == 200
    result = response.json()
    domain_result = toets(
        DakkapelInvoer(
            dakvlak=Dakvlak(body["dakvlak"]),
            dakvlak_naar_openbaar_toegankelijk_gebied=body[
                "dakvlak_naar_openbaar_toegankelijk_gebied"
            ],
            plat_dak=body["plat_dak"],
            hoogte_m=Decimal(body["hoogte_m"]),
            onderzijde_boven_dakvoet_m=Decimal(body["onderzijde_boven_dakvoet_m"]),
            bovenzijde_onder_daknok_m=Decimal(body["bovenzijde_onder_daknok_m"]),
            linker_zijkant_tot_dakvlakrand_m=Decimal(body["linker_zijkant_tot_dakvlakrand_m"]),
            rechter_zijkant_tot_dakvlakrand_m=Decimal(body["rechter_zijkant_tot_dakvlakrand_m"]),
            monumentrelatie=Monumentrelatie(body["monumentrelatie"]),
            gebiedsbescherming=Gebiedsbescherming(body["gebiedsbescherming"]),
        )
    )
    expected = DakkapelRuleResponse.model_validate(
        domain_result,
        from_attributes=True,
    )
    assert result == json.loads(expected.model_dump_json())
    assert result["eindoordeel"] == "waarschijnlijk_vergunningvrij"
    assert result["eisen"][0]["eis"] == "locatie"
    assert result["eisen"][2]["voldaan"] is True
    assert result["eisen"][2]["citaat"] == (
        "gemeten vanaf de voet van de dakkapel niet hoger dan 1,75 m;"
    )
    assert result["eisen"][2]["bron"]["bwb_id"] == "BWBR0041297"
    assert result["technische_bouwactiviteit"]["artikel"] == ("Bbl 2.27, tweede lid, onder a")
    assert result["voorbehoud"].startswith("Onverminderd regels in het omgevingsplan")
    assert result["vergunningcheck_url"] == "https://omgevingswet.overheid.nl/checken"


def test_endpoint_preserves_unknown_monument_and_null_measurements() -> None:
    response = _post(
        _body(
            monumentrelatie="onbekend",
            hoogte_m=None,
            onderzijde_boven_dakvoet_m=None,
            bovenzijde_onder_daknok_m=None,
            linker_zijkant_tot_dakvlakrand_m=None,
            rechter_zijkant_tot_dakvlakrand_m=None,
        )
    )

    assert response.status_code == 200
    result = response.json()
    assert result["eindoordeel"] == "onbepaald"
    assert "Vraag na" in result["advies"]


@pytest.mark.parametrize(
    ("field", "value", "eis", "expected"),
    [
        ("hoogte_m", "1.75", "hoogte", True),
        ("hoogte_m", "1.7500000001", "hoogte", False),
        ("onderzijde_boven_dakvoet_m", "0.5", "onderzijde", False),
        ("onderzijde_boven_dakvoet_m", "1", "onderzijde", False),
        ("onderzijde_boven_dakvoet_m", "0.5001", "onderzijde", True),
        ("onderzijde_boven_dakvoet_m", "0.9999", "onderzijde", True),
        ("bovenzijde_onder_daknok_m", "0.5", "bovenzijde", False),
        ("bovenzijde_onder_daknok_m", "0.5001", "bovenzijde", True),
        ("linker_zijkant_tot_dakvlakrand_m", "0.5", "linker_zijkant", False),
        ("linker_zijkant_tot_dakvlakrand_m", "0.5001", "linker_zijkant", True),
        ("rechter_zijkant_tot_dakvlakrand_m", "0.5", "rechter_zijkant", False),
        ("rechter_zijkant_tot_dakvlakrand_m", "0.5001", "rechter_zijkant", True),
    ],
)
def test_endpoint_returns_domain_boundary_outcome(
    field: str,
    value: str,
    eis: str,
    expected: bool,
) -> None:
    response = _post(_body(**{field: value}))

    assert response.status_code == 200
    result = response.json()
    matching = next(item for item in result["eisen"] if item["eis"] == eis)
    assert matching["voldaan"] is expected


@pytest.mark.parametrize(
    "field",
    [
        "hoogte_m",
        "onderzijde_boven_dakvoet_m",
        "bovenzijde_onder_daknok_m",
        "linker_zijkant_tot_dakvlakrand_m",
        "rechter_zijkant_tot_dakvlakrand_m",
    ],
)
@pytest.mark.parametrize("value", ["01", "1.0", "1,5", "1e0", -1, 1.5])
def test_measurements_require_canonical_decimal_strings(field: str, value: object) -> None:
    response = _post(_body(**{field: value}))

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["dakvlak_naar_openbaar_toegankelijk_gebied", "plat_dak"])
@pytest.mark.parametrize("value", [0, 1, "true", "false"])
def test_boolean_fields_require_json_booleans_or_null(field: str, value: object) -> None:
    response = _post(_body(**{field: value}))

    assert response.status_code == 422


def test_openapi_registers_rule_contract_and_canonical_decimal_pattern() -> None:
    schema = build_openapi_spec()
    post = schema["paths"]["/api/rules/dakkapel"]["post"]
    request_schema = schema["components"]["schemas"]["DakkapelRuleRequest"]
    height_schema = request_schema["properties"]["hoogte_m"]
    string_schema = next(
        option for option in height_schema["anyOf"] if option.get("type") == "string"
    )

    assert post["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DakkapelRuleRequest"
    )
    assert post["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DakkapelRuleResponse"
    )
    assert string_schema["pattern"] == r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$"
