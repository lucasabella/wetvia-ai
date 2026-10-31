"""Thin command wiring for the injected BWB ingest service."""

from __future__ import annotations

from typer.testing import CliRunner

from wetvia.cli import build_cli
from wetvia.ingest import EmbeddingReport, IngestReport


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


class _FakeEmbeddingJob:
    def __init__(self) -> None:
        self.calls: list[dict[str, int | None]] = []

    async def run(
        self, *, max_batches: int = 100, batch_size: int | None = None
    ) -> EmbeddingReport:
        self.calls.append({"max_batches": max_batches, "batch_size": batch_size})
        return EmbeddingReport(batches=2, embedded=5, skipped_stale=1, batch_limit_reached=True)


def _build_cli(service: _FakeService, job_factory: object | None = None):
    factory = job_factory or _FakeEmbeddingJob
    return build_cli(service, factory)  # type: ignore[arg-type]


def test_bwb_ingest_cli_passes_preset_to_injected_service() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(_build_cli(service), ["ingest", "bwb", "--preset", "mvp"])

    assert result.exit_code == 0, result.output
    assert service.ingest_calls == [{"preset": "mvp", "ids": None}]
    assert "1 regulations, 2 Toestand(s), 5 chunks" in result.output


def test_bwb_ingest_cli_accepts_repeated_ids() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(
        _build_cli(service),
        ["ingest", "bwb", "--ids", "BWBR0041297", "--ids", "BWBR0005537"],
    )

    assert result.exit_code == 0, result.output
    assert service.ingest_calls == [{"preset": None, "ids": ["BWBR0041297", "BWBR0005537"]}]


def test_bwb_ingest_cli_reports_missing_selection_as_usage_error() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(_build_cli(service), ["ingest", "bwb"])

    assert result.exit_code == 2
    assert "specify exactly one of preset or ids" in result.output


def test_bwb_ingest_cli_rejects_conflicting_selection_options() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(
        _build_cli(service),
        ["ingest", "bwb", "--preset", "mvp", "--ids", "BWBR0041297"],
    )

    assert result.exit_code == 2
    assert "specify exactly one of preset or ids" in result.output


def test_bwb_ingest_cli_rejects_unknown_preset() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(_build_cli(service), ["ingest", "bwb", "--preset", "unknown"])

    assert result.exit_code == 2
    assert "unknown BWB preset: unknown" in result.output


def test_sync_cli_delegates_to_injected_service() -> None:
    service = _FakeService()
    runner = CliRunner()

    result = runner.invoke(_build_cli(service), ["ingest", "sync"])

    assert result.exit_code == 0, result.output
    assert service.sync_calls == 1
    assert "1 regulations, 1 Toestand(s), 3 chunks" in result.output


def test_embedding_cli_is_bounded_and_constructs_job_only_when_invoked() -> None:
    service = _FakeService()
    job = _FakeEmbeddingJob()
    factory_calls = 0

    def make_job() -> _FakeEmbeddingJob:
        nonlocal factory_calls
        factory_calls += 1
        return job

    cli = build_cli(service, make_job)  # type: ignore[arg-type]
    assert factory_calls == 0
    result = CliRunner().invoke(cli, ["embed", "--max-batches", "2", "--batch-size", "3"])

    assert result.exit_code == 0, result.output
    assert factory_calls == 1
    assert job.calls == [{"max_batches": 2, "batch_size": 3}]
    assert "5 chunks in 2 batch(es)" in result.output
    assert "run again to continue" in result.output


def test_embedding_cli_rejects_non_positive_batch_limits() -> None:
    cli = _build_cli(_FakeService())
    runner = CliRunner()

    batch_limit_result = runner.invoke(cli, ["embed", "--max-batches", "0"])
    batch_size_result = runner.invoke(cli, ["embed", "--batch-size", "0"])

    assert batch_limit_result.exit_code == 2
    assert batch_size_result.exit_code == 2
