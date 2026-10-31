"""Batch command composition stays in the application bootstrap."""

from __future__ import annotations

import pytest

import wetvia.bootstrap as bootstrap
from wetvia.config import Settings


def test_run_cli_composes_ingest_dependencies_without_constructing_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    embedding_job_factories = []

    class FakeEngine:
        async def dispose(self) -> None:
            events.append("dispose")

    class FakeSource:
        def __enter__(self) -> FakeSource:
            events.append("source-enter")
            return self

        def __exit__(self, *_: object) -> None:
            events.append("source-exit")

    class FakeCli:
        def __call__(self) -> None:
            events.append("cli")

    class FakeEmbedder:
        dimension = 1024
        model_id = "stub/multilingual-e5"

    fake_engine = FakeEngine()
    monkeypatch.setattr(
        bootstrap,
        "create_db_engine",
        lambda database_url: events.append(f"engine:{database_url}") or fake_engine,
    )
    monkeypatch.setattr(
        bootstrap,
        "create_session_factory",
        lambda supplied_engine: events.append("session-factory") or "sessions",
    )
    monkeypatch.setattr(bootstrap, "BwbSRUClient", FakeSource)
    monkeypatch.setattr(
        bootstrap,
        "IngestService",
        lambda sessions, source: events.append("service") or "service",
    )
    monkeypatch.setattr(
        bootstrap,
        "build_cli",
        lambda service, embedding_job_factory: (
            events.append("build-cli")
            or embedding_job_factories.append(embedding_job_factory)
            or FakeCli()
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "SentenceTransformersEmbedder",
        lambda *args, **kwargs: events.append("model-load") or FakeEmbedder(),
    )

    def reject_llm(_: Settings) -> object:
        raise AssertionError("batch ingestion must not construct an LLM provider")

    monkeypatch.setattr(bootstrap, "get_provider", reject_llm)
    bootstrap.run_cli(Settings(database_url="postgresql+psycopg://test@localhost/wetvia_test"))

    assert events == [
        "engine:postgresql+psycopg://test@localhost/wetvia_test",
        "source-enter",
        "session-factory",
        "service",
        "build-cli",
        "cli",
        "source-exit",
        "dispose",
    ]
    assert len(embedding_job_factories) == 1
    assert "model-load" not in events
    embedding_job_factories[0]()
    assert events[-1] == "model-load"
