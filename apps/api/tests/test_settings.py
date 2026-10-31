"""Settings stay out of logs and out of modules other than bootstrap."""

import pytest
from pydantic import SecretStr, ValidationError

from wetvia.bootstrap import build_app
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
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_dimension=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, embedding_batch_size=0)


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
    assert context.llm_provider == "openai_compat"
    assert "not-a-real-key" not in repr(app.state)
