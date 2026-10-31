"""Batch command composition stays in the application bootstrap."""

from __future__ import annotations

import pytest

import wetvia.bootstrap as bootstrap
from wetvia.config import Settings
from wetvia.llm.adapters.fake import FakeProvider


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


@pytest.mark.parametrize(
    ("provider", "mode"),
    [("ollama", "local"), ("openai_compat", "cloud")],
)
def test_build_app_injects_chat_mode_without_loading_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    mode: str,
) -> None:
    class FakeEngine:
        async def dispose(self) -> None:
            return None

    engine = FakeEngine()
    monkeypatch.setattr(bootstrap, "create_db_engine", lambda _url: engine)
    monkeypatch.setattr(bootstrap, "create_session_factory", lambda _engine: object())
    monkeypatch.setattr(bootstrap, "get_provider", lambda _settings: FakeProvider([]))

    def fail_if_model_loads(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the embedding model must stay lazy during app construction")

    monkeypatch.setattr(bootstrap, "SentenceTransformersEmbedder", fail_if_model_loads)
    app = bootstrap.build_app(
        Settings(
            database_url="postgresql+psycopg://test@localhost/wetvia_test",
            llm_provider=provider,  # type: ignore[arg-type]
        )
    )

    assert app.state.answer_pipeline is not None
    assert app.state.chat_mode == mode
    assert app.state.retriever is not None
