"""Deterministic OpenAPI export without constructing runtime services."""

import json
from pathlib import Path
from typing import Any

from wetvia.api import create_app
from wetvia.api.deps import HealthContext
from wetvia.db.engine import DbStatus


async def _inert_database_check() -> DbStatus:
    """Satisfy the app factory without connecting to a database."""
    return "ok"


def build_openapi_spec() -> dict[str, Any]:
    """Build the spec from an app factory and an inert health context."""
    context = HealthContext(
        version="0.0.0",
        check_db=_inert_database_check,
    )
    return create_app(context).openapi()


def export_openapi(destination: Path) -> None:
    """Write a stable, UTF-8 OpenAPI document without app startup or I/O."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = json.dumps(
        build_openapi_spec(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    destination.write_text(f"{document}\n", encoding="utf-8")


__all__ = ["build_openapi_spec", "export_openapi"]
