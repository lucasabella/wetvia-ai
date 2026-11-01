"""Settings stay out of logs and out of modules other than bootstrap."""

import asyncio

import pytest
from pydantic import SecretStr, ValidationError

from wetvia.bootstrap import build_app, get_chat_providers
from wetvia.config import Settings
from wetvia.core import LlmProvider


def _settings(
    *,
    llm_provider: LlmProvider = "ollama",
    llm_api_key: str | None = None,
) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://wetvia:change-me@127.0.0.1:5432/wetvia",
        llm_provider=llm_provider,
        llm_base_url="http://127.0.0.1:11434",
        llm_model="qwen3.5:9b",
        cloud_llm_base_url="https://api.scaleway.ai/v1",
        cloud_llm_model="qwen3.8-27b",
        embedding_model="intfloat/multilingual-e5-large-instruct",
        llm_api_key=llm_api_key,
    )


def test_api_key_is_secret_and_absent_when_empty() -> None:
    with_key = _settings(llm_api_key="not-a-real-key")
    assert isinstance(with_key.llm_api_key, SecretStr)
    assert with_key.llm_api_key.get_secret_value() == "not-a-real-key"
    assert "not-a-real-key" not in repr(with_key)

    assert _settings(llm_api_key="").llm_api_key is None
    assert _settings(llm_api_key=None).llm_api_key is None


def test_llm_provider_is_limited() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "database_url": "postgresql+psycopg://wetvia:change-me@127.0.0.1:5432/wetvia",
                "llm_provider": "paid-vendor",
                "llm_base_url": "http://127.0.0.1:11434",
                "llm_model": "qwen3.5:9b",
                "embedding_model": "intfloat/multilingual-e5-large-instruct",
            }
        )


def test_embedding_settings_have_safe_vector_defaults_and_require_positive_values() -> None:
    settings = _settings()

    assert settings.embedding_model == "intfloat/multilingual-e5-large-instruct"
    assert settings.embedding_dimension == 1024
    assert settings.embedding_batch_size == 32
    assert settings.answer_abstention_tau == 0.01
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_dimension=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_batch_size=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, answer_abstention_tau=1.1)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, answer_abstention_tau=float("nan"))


def test_answer_abstention_tau_is_configurable_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANSWER_ABSTENTION_TAU", "0.125")

    settings = Settings(_env_file=None)

    assert settings.answer_abstention_tau == 0.125


def test_asgi_app_attribute_is_built_once() -> None:
    import wetvia.bootstrap as bootstrap

    bootstrap._app = None
    first = bootstrap.app
    second = bootstrap.app
    assert first is second
    assert bootstrap._app is first


def test_build_app_uses_passed_settings_without_reading_a_new_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    app = build_app(_settings(llm_provider="openai_compat", llm_api_key="not-a-real-key"))
    context = app.state.health_context
    assert context.local_configured is True
    assert context.cloud_configured is True
    assert set(app.state.llm_providers) == {"local", "cloud"}
    assert set(app.state.answer_pipelines) == {"local", "cloud"}
    assert app.state.answer_pipelines["local"]._provider is app.state.llm_providers["local"]
    assert app.state.answer_pipelines["cloud"]._provider is app.state.llm_providers["cloud"]
    assert app.state.answer_pipelines["local"] is not app.state.answer_pipelines["cloud"]
    assert "not-a-real-key" not in repr(app.state)


def test_build_app_injects_retriever_without_loading_embedding_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wetvia.bootstrap as bootstrap

    def reject_model_load(*args: object, **kwargs: object) -> object:
        raise AssertionError("model loading must wait until a search request")

    monkeypatch.setattr(bootstrap, "SentenceTransformersEmbedder", reject_model_load)
    app = build_app(_settings())

    assert app.state.retriever is not None
    assert app.state.retriever._embedder.model_id == "intfloat/multilingual-e5-large-instruct"
    assert app.state.retriever._embedder.dimension == 1024
    assert app.state.answer_pipelines["local"]._retriever is app.state.retriever
    assert app.state.answer_pipelines["local"]._provider is app.state.llm_providers["local"]
    assert app.state.answer_pipelines["local"]._abstention_tau == 0.01


def test_legacy_cloud_env_does_not_become_local_url_or_claim_scaleway() -> None:
    legacy = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://wetvia:change-me@127.0.0.1:5432/wetvia",
        llm_provider="openai_compat",
        llm_base_url="https://legacy.example.test/v1",
        llm_model="legacy-model",
        llm_api_key="not-a-real-key",
    )

    assert legacy.llm_base_url == "http://127.0.0.1:11434"
    assert legacy.llm_model == "qwen3.5:9b"
    assert legacy.cloud_llm_base_url == "https://legacy.example.test/v1"
    assert legacy.cloud_llm_model == "legacy-model"
    app = build_app(legacy)
    assert app.state.health_context.local_configured is True
    assert app.state.health_context.cloud_configured is False
    assert set(app.state.answer_pipelines) == {"local"}


def test_legacy_cloud_environment_variables_are_migrated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_BASE_URL", "https://legacy.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "legacy-model")
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key")

    settings = Settings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:11434"
    assert settings.llm_model == "qwen3.5:9b"
    assert settings.cloud_llm_base_url == "https://legacy.example.test/v1"
    assert settings.cloud_llm_model == "legacy-model"


def test_blank_provider_settings_are_not_reported_as_configured() -> None:
    settings = Settings(
        _env_file=None,
        llm_base_url=" ",
        llm_model="local-model",
        cloud_llm_base_url="https://api.scaleway.ai/v1",
        cloud_llm_model=" ",
        llm_api_key=" ",
    )

    assert get_chat_providers(settings) == {}


@pytest.mark.parametrize("api_key", [None, " "])
def test_cloud_requires_a_nonblank_key_even_with_the_pinned_endpoint(
    api_key: str | None,
) -> None:
    settings = Settings(
        _env_file=None,
        cloud_llm_base_url="https://api.scaleway.ai/v1",
        cloud_llm_model="configured-model",
        llm_api_key=api_key,
    )

    assert set(get_chat_providers(settings)) == {"local"}


def test_open_retriever_exposes_public_runtime_and_closes_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import wetvia.bootstrap as bootstrap

    class _Engine:
        disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    engine = _Engine()
    monkeypatch.setattr(bootstrap, "create_db_engine", lambda _: engine)
    monkeypatch.setattr(bootstrap, "create_session_factory", lambda _: object())

    def reject_model_load(*args: object, **kwargs: object) -> object:
        raise AssertionError("bootstrap must keep the embedding adapter lazy")

    monkeypatch.setattr(bootstrap, "SentenceTransformersEmbedder", reject_model_load)

    async def exercise() -> None:
        async with bootstrap.open_retriever(_settings()) as runtime:
            assert runtime.model_id == "intfloat/multilingual-e5-large-instruct"
            assert runtime.dimension == 1024
            assert runtime.retriever is not None
            assert not engine.disposed
        assert engine.disposed

    asyncio.run(exercise())
