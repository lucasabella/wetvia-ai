"""Shared types. No I/O and no settings."""

from typing import Literal

LlmProvider = Literal["ollama", "openai_compat"]

__all__ = ["LlmProvider"]
