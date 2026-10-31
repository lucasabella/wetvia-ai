"""Thin command wiring for the injected BWB ingest service."""

from __future__ import annotations

from typer.testing import CliRunner

from wetvia.cli import build_cli
from wetvia.ingest import IngestReport


class _FakeService:
    def __init__(self) -> None:
        self.ingest_calls: list[dict[str, object]] = []
        self.sync_calls = 0

    async def ingest_bwb(self, **kwargs: object) -> IngestReport:
        preset = kwargs.get("preset")
        ids = kwargs.get("ids")
        if (preset is None) == (ids is None):
            raise ValueError("specify exactly one of preset or ids")
        if preset is not None and preset != "mvp":
            raise ValueError(f"unknown BWB preset: {preset}")
        self.ingest_calls.append(kwargs)
        return IngestReport(bwb_ids=("BWBR0041297",), toestanden=2, chunks=5)

    async def sync(self) -> IngestReport:
        self.sync_calls += 1
        return IngestReport(bwb_ids=("BWBR0041297",), toestanden=1, chunks=3)


def test_bwb_ingest_cli_passes_preset_to_injected_service() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(build_cli(service), ["ingest", "bwb", "--preset", "mvp"])

    assert result.exit_code == 0, result.output
    assert service.ingest_calls == [{"preset": "mvp", "ids": None}]
    assert "1 regulations, 2 Toestand(s), 5 chunks" in result.output


def test_bwb_ingest_cli_accepts_repeated_ids() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(
        build_cli(service),
        ["ingest", "bwb", "--ids", "BWBR0041297", "--ids", "BWBR0005537"],
    )

    assert result.exit_code == 0, result.output
    assert service.ingest_calls == [{"preset": None, "ids": ["BWBR0041297", "BWBR0005537"]}]


def test_bwb_ingest_cli_reports_missing_selection_as_usage_error() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(build_cli(service), ["ingest", "bwb"])

    assert result.exit_code == 2
    assert "specify exactly one of preset or ids" in result.output


def test_bwb_ingest_cli_rejects_conflicting_selection_options() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(
        build_cli(service),
        ["ingest", "bwb", "--preset", "mvp", "--ids", "BWBR0041297"],
    )

    assert result.exit_code == 2
    assert "specify exactly one of preset or ids" in result.output


def test_bwb_ingest_cli_rejects_unknown_preset() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(build_cli(service), ["ingest", "bwb", "--preset", "unknown"])

    assert result.exit_code == 2
    assert "unknown BWB preset: unknown" in result.output


def test_sync_cli_delegates_to_injected_service() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(build_cli(service), ["ingest", "sync"])

    assert result.exit_code == 0, result.output
    assert service.sync_calls == 1
    assert "1 regulations, 1 Toestand(s), 3 chunks" in result.output
