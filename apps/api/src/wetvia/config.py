"""Process settings. Only ``wetvia.bootstrap`` may construct this."""

from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from wetvia.core import LlmProvider

_REPO_ROOT = Path(__file__).resolve().parents[4]
_API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-backed settings. ``llm_api_key`` is a ``SecretStr`` and must not be logged."""

    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), str(_API_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+psycopg://wetvia:change-me@127.0.0.1:5432/wetvia"
    llm_provider: LlmProvider = "ollama"
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3.5:9b"
    llm_api_key: SecretStr | None = None
    embedding_model: str = "intfloat/multilingual-e5-large-instruct"

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def empty_api_key_is_absent(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value
