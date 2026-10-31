"""Validated JSONL input for retrieval evaluation; no legal dataset is bundled."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

Category = Literal["A", "B", "C", "D", "E", "F"]
ExpectedStatus = Literal["beantwoord", "onzeker", "buiten_scope"]
ArticleKey = tuple[str, str]


class GoldenSource(BaseModel):
    """Ground-truth citation fields; metrics intentionally score article-level keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bwb_id: str = Field(min_length=1)
    artikel: str = Field(min_length=1)
    onderdeel: str | None

    @field_validator("bwb_id", "artikel", mode="before")
    @classmethod
    def nonempty_source_text(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("onderdeel", mode="before")
    @classmethod
    def normalize_part(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be null or a non-empty string")
        return value.strip()

    @property
    def article_key(self) -> ArticleKey:
        return self.bwb_id, self.artikel


class RetrievalEvalItem(BaseModel):
    """One labeled retrieval query. Set ``concept`` on all unreviewed fixtures."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    vraag: str = Field(min_length=1)
    categorie: Category
    peildatum: date
    gouden_bronnen: list[GoldenSource]
    kernfeiten: list[str]
    verwachte_status: ExpectedStatus
    concept: bool = Field(strict=True)

    @field_validator("id", "vraag", mode="before")
    @classmethod
    def nonempty_text(cls, value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    @field_validator("peildatum", mode="before")
    @classmethod
    def strict_iso_date(cls, value: object) -> object:
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError("must use YYYY-MM-DD")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("must be a valid calendar date in YYYY-MM-DD format") from exc

    @field_validator("kernfeiten")
    @classmethod
    def nonempty_facts(cls, value: list[str]) -> list[str]:
        if any(not fact.strip() for fact in value):
            raise ValueError("items must be non-empty strings")
        return [fact.strip() for fact in value]

    @property
    def golden_articles(self) -> frozenset[ArticleKey]:
        return frozenset(source.article_key for source in self.gouden_bronnen)


def load_retrieval_dataset(
    path: Path,
    *,
    raw_bytes: bytes | None = None,
) -> list[RetrievalEvalItem]:
    """Load an explicitly selected JSONL dataset with line-specific validation errors."""
    if raw_bytes is None and not path.is_file():
        raise ValueError(f"dataset file does not exist: {path}")
    content = path.read_bytes() if raw_bytes is None else raw_bytes
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: dataset is not valid UTF-8") from exc

    items: list[RetrievalEvalItem] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            parsed: object = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON ({exc.msg})") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{path}:{line_number}: each line must be a JSON object")
        try:
            item = RetrievalEvalItem.model_validate(parsed)
        except ValidationError as exc:
            messages = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors(include_url=False)
            )
            raise ValueError(f"{path}:{line_number}: invalid eval item: {messages}") from exc
        if item.id in seen_ids:
            raise ValueError(f"{path}:{line_number}: duplicate id {item.id!r}")
        seen_ids.add(item.id)
        items.append(item)
    return items
