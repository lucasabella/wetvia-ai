"""OpenAPI export is stable and does not initialize runtime dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import wetvia.bootstrap as bootstrap
from wetvia.api.openapi_export import export_openapi


def _references(value: Any) -> list[str]:
    if isinstance(value, dict):
        found = [value["$ref"]] if isinstance(value.get("$ref"), str) else []
        return found + [reference for child in value.values() for reference in _references(child)]
    if isinstance(value, list):
        return [reference for child in value for reference in _references(child)]
    return []


def test_export_is_deterministic_offline_and_includes_sse_union(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_if_runtime_is_initialized(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("OpenAPI export must not construct runtime services")

    monkeypatch.setattr(bootstrap, "build_app", fail_if_runtime_is_initialized)
    monkeypatch.setattr(bootstrap, "create_db_engine", fail_if_runtime_is_initialized)
    monkeypatch.setattr(bootstrap, "get_provider", fail_if_runtime_is_initialized)
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")
    monkeypatch.setenv("LLM_PROVIDER", "not-a-provider")

    first = tmp_path / "first" / "openapi.json"
    second = tmp_path / "second" / "openapi.json"
    export_openapi(first)
    export_openapi(second)

    first_bytes = first.read_bytes()
    assert first_bytes == second.read_bytes()
    document = json.loads(first_bytes)
    assert document["openapi"].startswith("3.1.")
    schemas = document["components"]["schemas"]
    assert "ChatEvent" in schemas
    assert "ChatSourcesEvent" in schemas
    assert "ChatAnswerEvent" in schemas
    assert "ChatErrorEvent" in schemas
    assert "ChatDoneEvent" in schemas
    assert "verifier_notes" in schemas["VerifiedAnswer"]["properties"]
    assert "#/components/schemas/VerifiedAnswer" in _references(schemas["ChatAnswerEvent"])
    for reference in _references(document):
        if reference.startswith("#/components/schemas/"):
            name = reference.removeprefix("#/components/schemas/")
            assert name in schemas, f"unresolved schema reference {reference}"
