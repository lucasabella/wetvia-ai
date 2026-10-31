"""Injected retrieval-to-answer pipeline with source-label validation."""

from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import date, datetime
from importlib.resources import files
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from wetvia.answer.schema import AnswerPoint, AnswerStatus, AnswerV1, FollowUpStep
from wetvia.llm import ChatMessage, LLMProvider
from wetvia.retrieval import Retriever, ScoredChunk, SourceDocument

MAX_SOURCE_TOKENS = 8000
MAX_SOURCES = 8
ANSWER_TEMPERATURE = 0.2
ANSWER_SEARCH_MODE: Literal["hybrid"] = "hybrid"


class SourceTokenCounter(Protocol):
    """Count tokens, or return a documented conservative token upper bound."""

    def count_tokens(self, text: str) -> int:
        """Return a non-negative count for this exact rendered source block."""


class Utf8ByteUpperBoundCounter:
    """Use UTF-8 byte length as a conservative upper bound, never as an exact count.

    For byte-level tokenizers each emitted token represents at least one input byte,
    so this may truncate earlier than a model tokenizer would. Deployments with the
    exact generator tokenizer can inject that counter instead.
    """

    def count_tokens(self, text: str) -> int:
        return len(text.encode("utf-8"))


class AnswerDateMismatchError(ValueError):
    """The model returned an answer for a date other than the requested peildatum."""


class UnknownSourceLabelError(ValueError):
    """The model cited a label that was not assigned to a sent source."""


def _validate_summary(value: str) -> str:
    if not value.strip():
        raise ValueError("samenvatting mag niet leeg zijn")
    if len(value.split()) > 80:
        raise ValueError("samenvatting mag maximaal 80 woorden bevatten")
    return value


def _validate_nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("tekst mag niet leeg zijn")
    return value


class _AnswerDraftPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tekst: str = Field(min_length=1)
    bron_ids: list[Annotated[str, Field(pattern=r"^\[[1-8]\]$")]] = Field(min_length=1)

    _nonblank_text = field_validator("tekst")(_validate_nonblank)

    @field_validator("bron_ids")
    @classmethod
    def labels_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("bron_ids moeten uniek zijn")
        return value


class _AnswerDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AnswerStatus
    samenvatting: str = Field(min_length=1)
    punten: list[_AnswerDraftPoint]
    voorbehouden: list[str]
    vervolgstappen: list[FollowUpStep]
    peildatum: date

    _summary_limit = field_validator("samenvatting")(_validate_summary)

    @field_validator("voorbehouden")
    @classmethod
    def caveats_must_be_nonblank(cls, value: list[str]) -> list[str]:
        for caveat in value:
            _validate_nonblank(caveat)
        return value

    @model_validator(mode="after")
    def answered_status_has_points(self) -> _AnswerDraft:
        if self.status == "beantwoord" and not self.punten:
            raise ValueError("een beantwoord antwoord moet minstens één bronpunt bevatten")
        return self


def _validate_peildatum(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("peildatum must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError("peildatum must use YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("peildatum must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise ValueError("peildatum must use YYYY-MM-DD")
    return parsed


def _load_prompt() -> str:
    return files("wetvia.answer.prompts").joinpath("answer_nl.md").read_text(encoding="utf-8")


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


class AnswerPipeline:
    """Create cited answers from the public Retriever and LLMProvider ports."""

    def __init__(
        self,
        retriever: Retriever,
        provider: LLMProvider,
        *,
        token_counter: SourceTokenCounter | None = None,
        max_source_tokens: int = MAX_SOURCE_TOKENS,
        system_prompt: str | None = None,
    ) -> None:
        if max_source_tokens <= 0 or max_source_tokens > MAX_SOURCE_TOKENS:
            raise ValueError(f"max_source_tokens must be between 1 and {MAX_SOURCE_TOKENS}")
        self._retriever = retriever
        self._provider = provider
        self._counter = token_counter if token_counter is not None else Utf8ByteUpperBoundCounter()
        self._max_source_tokens = max_source_tokens
        self._system_prompt = system_prompt or _load_prompt()

    async def answer(self, vraag: str, peildatum: date | str) -> AnswerV1:
        """Retrieve up to eight hybrid chunks and return a validated AnswerV1."""
        requested_date = _validate_peildatum(peildatum)
        if not vraag.strip():
            raise ValueError("vraag mag niet leeg zijn")

        retrieved = await self._retriever.search(
            vraag.strip(),
            requested_date,
            k=MAX_SOURCES,
            include_future=False,
            mode=ANSWER_SEARCH_MODE,
        )
        source_context, label_to_source = self._source_context(retrieved)
        if not label_to_source:
            return _uncertain_without_sources(requested_date)

        messages = self._messages(vraag.strip(), requested_date, source_context)
        draft = await self._provider.chat(
            messages,
            _AnswerDraft,
            False,
            ANSWER_TEMPERATURE,
        )
        if not isinstance(draft, _AnswerDraft):
            raise TypeError("LLMProvider returned a value outside the structured answer schema")
        if draft.peildatum != requested_date:
            actual_date = draft.peildatum.isoformat()
            expected_date = requested_date.isoformat()
            raise AnswerDateMismatchError(
                f"model returned peildatum {actual_date}, expected {expected_date}"
            )

        points: list[AnswerPoint] = []
        for point in draft.punten:
            source_ids: list[UUID] = []
            for label in point.bron_ids:
                source_id = label_to_source.get(label)
                if source_id is None:
                    raise UnknownSourceLabelError(f"model cited unknown source label {label!r}")
                source_ids.append(source_id)
            points.append(AnswerPoint(tekst=point.tekst, bron_ids=source_ids))

        return AnswerV1(
            status=draft.status,
            samenvatting=draft.samenvatting,
            punten=points,
            voorbehouden=draft.voorbehouden,
            vervolgstappen=draft.vervolgstappen,
            peildatum=requested_date,
        )

    def _messages(
        self,
        vraag: str,
        peildatum: date,
        source_context: str,
    ) -> list[ChatMessage]:
        user_content = (
            f"Peildatum: {peildatum.isoformat()}\n"
            f"Vraag: {vraag}\n\n"
            "Gebruik voor `bron_ids` uitsluitend de zichtbare labels uit deze BRONNEN.\n"
            "BRONNEN:\n"
            f"{source_context}"
        )
        return [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

    def _source_context(
        self,
        retrieved: Sequence[ScoredChunk],
    ) -> tuple[str, dict[str, UUID]]:
        candidates = [
            result.source for result in retrieved[:MAX_SOURCES] if result.source.tekst.strip()
        ]
        if not candidates:
            return "", {}

        blocks: list[str] = []
        label_to_source: dict[str, UUID] = {}
        used = 0
        for index, source in enumerate(candidates):
            remaining_slots = len(candidates) - index
            separator = self._count("\n\n") if blocks else 0
            allowance = (self._max_source_tokens - used - separator) // remaining_slots
            if allowance <= 0:
                break
            label = f"[{len(blocks) + 1}]"
            block: str | None = None
            accepted = False
            while allowance > 0:
                block = self._fit_source(source, label, allowance)
                if block is None:
                    break
                candidate_context = "\n\n".join((*blocks, block))
                candidate_count = self._count(candidate_context)
                if candidate_count <= self._max_source_tokens:
                    used = candidate_count
                    accepted = True
                    break
                allowance -= max(1, candidate_count - self._max_source_tokens)
            if block is None or not accepted:
                continue
            blocks.append(block)
            label_to_source[label] = source.chunk_id
        return "\n\n".join(blocks), label_to_source

    def _fit_source(self, source: SourceDocument, label: str, budget: int) -> str | None:
        metadata = source.metadata
        text = source.tekst

        def render(body: str, truncated: bool) -> str:
            suffix = " [tekst afgekapt]" if truncated else ""
            end_date = metadata.geldig_tot.isoformat() if metadata.geldig_tot else "onbepaald"
            fields = (
                f"Regeling: {_escape(metadata.regeling_titel)}",
                f"BWB-id: {_escape(metadata.bwb_id)}",
                f"Artikel: {_escape(metadata.artikel)}",
                f"Lid: {_escape(metadata.lid or 'niet vermeld')}",
                f"Onderdeel: {_escape(metadata.onderdeel or 'niet vermeld')}",
                f"Geldigheid: {_escape(metadata.geldig_vanaf.isoformat())} t/m {_escape(end_date)}",
                f"Status op peildatum: {_escape(metadata.status)}",
                f"Bron URL: {_escape(metadata.bron_url)}",
                "Tekst:",
                f"{_escape(body)}{suffix}",
            )
            return f'<bron id="{label.strip("[]")}">\n' + "\n".join(fields) + "\n</bron>"

        full = render(text, False)
        if self._count(full) <= budget:
            return full

        low, high = 0, len(text) - 1
        best: str | None = None
        best_prefix = ""
        while low <= high:
            midpoint = (low + high) // 2
            prefix = _truncate_at_boundary(text, midpoint)
            candidate = render(prefix, True)
            if prefix and self._count(candidate) <= budget:
                best = candidate
                best_prefix = prefix
                low = midpoint + 1
            else:
                high = midpoint - 1

        if best is None:
            candidate_length = max(1, len(text) // 2)
            while candidate_length > 0:
                prefix = _truncate_at_boundary(text, candidate_length)
                candidate = render(prefix, True)
                if prefix and self._count(candidate) <= budget:
                    best, best_prefix = candidate, prefix
                    break
                candidate_length //= 2

        while best is not None and self._count(best) > budget:
            next_length = max(0, len(best_prefix) - max(1, len(best_prefix) // 16))
            prefix = _truncate_at_boundary(text, next_length)
            best = render(prefix, True) if prefix else None
            best_prefix = prefix
        if best is None:
            return None
        return best

    def _count(self, rendered: str) -> int:
        count = self._counter.count_tokens(rendered)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("source token counter must return a non-negative integer")
        return count


def _truncate_at_boundary(text: str, limit: int) -> str:
    prefix = text[:limit].rstrip()
    if limit < len(text) and prefix:
        boundary = prefix.rfind(" ")
        if boundary >= max(1, len(prefix) * 3 // 4):
            prefix = prefix[:boundary].rstrip()
    return prefix


def _uncertain_without_sources(peildatum: date) -> AnswerV1:
    return AnswerV1(
        status="onzeker",
        samenvatting="Ik kan deze vraag niet beantwoorden met de gevonden bronnen.",
        punten=[],
        voorbehouden=["Er zijn geen bruikbare bronnen gevonden voor deze vraag."],
        vervolgstappen=[],
        peildatum=peildatum,
    )


__all__ = [
    "ANSWER_SEARCH_MODE",
    "ANSWER_TEMPERATURE",
    "MAX_SOURCES",
    "MAX_SOURCE_TOKENS",
    "AnswerDateMismatchError",
    "AnswerPipeline",
    "SourceTokenCounter",
    "UnknownSourceLabelError",
    "Utf8ByteUpperBoundCounter",
]
