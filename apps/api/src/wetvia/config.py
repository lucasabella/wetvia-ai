"""Process settings. Only ``wetvia.bootstrap`` may construct this."""

import math
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
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
    # Local settings retain their existing environment variable names.
    llm_base_url: str = "http://127.0.0.1:11434"
    llm_model: str = "qwen3.5:9b"
    cloud_llm_base_url: str = "https://api.scaleway.ai/v1"
    cloud_llm_model: str = "qwen3.8-27b"
    llm_api_key: SecretStr | None = None
    embedding_model: str = "intfloat/multilingual-e5-large-instruct"
    embedding_dimension: int = Field(default=1024, gt=0)
    embedding_batch_size: int = Field(default=32, gt=0)
    answer_abstention_tau: float = Field(default=0.01, ge=0, le=1)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_cloud_settings(cls, value: object) -> object:
        """Move a former single cloud endpoint out of the local Ollama settings."""
        if not isinstance(value, dict) or value.get("llm_provider") != "openai_compat":
            return value
        values = dict(value)
        if "cloud_llm_base_url" not in values and "llm_base_url" in values:
            values["cloud_llm_base_url"] = values["llm_base_url"]
        if "cloud_llm_model" not in values and "llm_model" in values:
            values["cloud_llm_model"] = values["llm_model"]
        values["llm_base_url"] = "http://127.0.0.1:11434"
        values["llm_model"] = "qwen3.5:9b"
        return values

    @field_validator("answer_abstention_tau")
    @classmethod
    def tau_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("answer_abstention_tau must be finite")
        return value

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def empty_api_key_is_absent(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value
