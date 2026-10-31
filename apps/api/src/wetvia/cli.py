"""Thin Typer commands that delegate all ingestion work to ``wetvia.ingest``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Annotated

import typer

from wetvia.ingest import EmbeddingJob, EmbeddingReport, IngestReport, IngestService


def build_cli(
    service: IngestService,
    embedding_job_factory: Callable[[], EmbeddingJob],
) -> typer.Typer:
    """Build the command tree with injected, lazily constructed use cases."""
    app = typer.Typer(no_args_is_help=True)
    ingest = typer.Typer(no_args_is_help=True)
    app.add_typer(ingest, name="ingest")

    @ingest.command("bwb")
    def ingest_bwb(
        preset: Annotated[str | None, typer.Option(help="Use a named BWB corpus preset.")] = None,
        ids: Annotated[
            list[str] | None,
            typer.Option("--ids", help="BWB-ID values; repeat --ids for multiple regulations."),
        ] = None,
    ) -> None:
        try:
            report = asyncio.run(service.ingest_bwb(preset=preset, ids=ids))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        _show_report("BWB ingest completed", report)

    @ingest.command("sync")
    def sync_bwb() -> None:
        report = asyncio.run(service.sync())
        _show_report("BWB sync completed", report)

    @app.command("embed")
    def embed(
        max_batches: Annotated[
            int,
            typer.Option(min=1, help="Maximum number of batches to process in this run."),
        ] = 100,
        batch_size: Annotated[
            int | None,
            typer.Option(min=1, help="Override the configured number of chunks per batch."),
        ] = None,
    ) -> None:
        report = asyncio.run(
            embedding_job_factory().run(max_batches=max_batches, batch_size=batch_size)
        )
        _show_embedding_report(report)

    return app


def _show_report(message: str, report: IngestReport) -> None:
    typer.echo(
        f"{message}: {len(report.bwb_ids)} regulations, "
        f"{report.toestanden} Toestand(s), {report.chunks} chunks"
    )


def _show_embedding_report(report: EmbeddingReport) -> None:
    message = (
        f"Embedding pass completed: {report.embedded} chunks in {report.batches} batch(es), "
        f"{report.skipped_stale} stale or already-filled rows skipped"
    )
    if report.batch_limit_reached:
        message += "; run again to continue"
    typer.echo(message)
