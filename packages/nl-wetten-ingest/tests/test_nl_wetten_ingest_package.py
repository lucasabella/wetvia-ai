"""Skelet: nl-wetten-ingest is importeerbaar en Apache-2.0."""

from __future__ import annotations

import importlib.metadata as metadata
from pathlib import Path

import nl_wetten_ingest


def test_package_imports() -> None:
    assert nl_wetten_ingest.__name__ == "nl_wetten_ingest"


def test_license_metadata_is_apache_2_0() -> None:
    info = metadata.metadata("nl-wetten-ingest")
    assert info["License-Expression"] == "Apache-2.0"


def test_license_file_is_apache_2_0() -> None:
    license_path = Path(__file__).resolve().parents[1] / "LICENSE"
    text = license_path.read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text


def test_py_typed_marker_is_present() -> None:
    package_dir = Path(nl_wetten_ingest.__file__).resolve().parent
    assert (package_dir / "py.typed").is_file()
