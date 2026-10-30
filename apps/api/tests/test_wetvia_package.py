"""Skelet: het API-pakket is importeerbaar en AGPL-3.0-only."""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
from pathlib import Path

import wetvia


def test_package_imports() -> None:
    assert wetvia.__name__ == "wetvia"


def test_subpackages_import() -> None:
    for name in (
        "wetvia.llm",
        "wetvia.llm.prompts",
        "wetvia.retrieval",
        "wetvia.rules",
        "wetvia.answer",
        "wetvia.dossier",
        "wetvia.db",
        "wetvia.api",
    ):
        importlib.import_module(name)


def test_license_metadata_is_agpl_3_0_only() -> None:
    info = metadata.metadata("wetvia-api")
    assert info["License-Expression"] == "AGPL-3.0-only"


def test_root_license_is_agpl() -> None:
    license_path = Path(__file__).resolve().parents[3] / "LICENSE"
    text = license_path.read_text(encoding="utf-8")
    assert text.startswith("                    GNU AFFERO GENERAL PUBLIC LICENSE")
