"""Thin Typer commands that delegate all ingestion work to ``wetvia.ingest``."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer

from wetvia.ingest import IngestReport, IngestService


def build_cli(service: IngestService) -> typer.Typer:
    """Build the command tree with an injected ingestion service."""
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

    return app


def _show_report(message: str, report: IngestReport) -> None:
    typer.echo(
        f"{message}: {len(report.bwb_ids)} regulations, "
        f"{report.toestanden} Toestand(s), {report.chunks} chunks"
    )
