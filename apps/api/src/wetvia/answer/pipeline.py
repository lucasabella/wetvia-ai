"""Injected retrieval-to-answer pipeline with source-label validation."""

from __future__ import annotations

import html
import math
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from typing import Any, Literal, Protocol, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

from wetvia.answer.schema import AnswerPoint, AnswerStatus, FollowUpStep, VerifiedAnswer
from wetvia.citations import (
    CitationClaim,
    CitationSource,
    retrieval_score_below_tau,
    verify_citations,
)
from wetvia.llm import ChatMessage, LLMProvider
from wetvia.retrieval import Retriever, ScoredChunk, SourceDocument

MAX_SOURCE_TOKENS = 8000
MAX_SOURCES = 8
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 8000
ANSWER_TEMPERATURE = 0.2
DEFAULT_ABSTENTION_TAU = 0.01
ANSWER_SEARCH_MODE: Literal["hybrid"] = "hybrid"
_REMOVAL_CAVEAT = "Een of meer beweringen zijn weggelaten omdat de bron ze niet bevestigde."


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


@dataclass(frozen=True, slots=True)
class IncludedAnswerSource:
    """One source that received a prompt label and was included in model context."""

    label: str
    source: SourceDocument
    score: float


IncludedSourcesHook = Callable[[Sequence[IncludedAnswerSource]], Awaitable[None]]


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
    bron_ids: list[str] = Field(min_length=1)

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


def _draft_schema(source_labels: Sequence[str]) -> type[BaseModel]:
    """Build a request schema whose citation enum contains only sent sources."""
    if not source_labels:
        raise ValueError("at least one source label is required")
    label_type: Any = Literal.__getitem__(tuple(source_labels))
    label_list_type: Any = list[label_type]
    point_model = create_model(
        "AnswerDraftPoint",
        __base__=_AnswerDraftPoint,
        bron_ids=(label_list_type, Field(min_length=1)),
    )
    point_list_type: Any = list[point_model]
    return create_model(
        "AnswerDraft",
        __base__=_AnswerDraft,
        punten=(point_list_type, Field()),
    )


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
        abstention_tau: float = DEFAULT_ABSTENTION_TAU,
        system_prompt: str | None = None,
    ) -> None:
        if max_source_tokens <= 0 or max_source_tokens > MAX_SOURCE_TOKENS:
            raise ValueError(f"max_source_tokens must be between 1 and {MAX_SOURCE_TOKENS}")
        if (
            isinstance(abstention_tau, bool)
            or not math.isfinite(abstention_tau)
            or not 0.0 <= abstention_tau <= 1.0
        ):
            raise ValueError("abstention_tau must be a finite number between 0 and 1")
        self._retriever = retriever
        self._provider = provider
        self._counter = token_counter if token_counter is not None else Utf8ByteUpperBoundCounter()
        self._max_source_tokens = max_source_tokens
        self._abstention_tau = abstention_tau
        self._system_prompt = system_prompt or _load_prompt()

    async def answer(
        self,
        vraag: str,
        peildatum: date | str,
        *,
        history: Sequence[ChatMessage] = (),
        on_sources: IncludedSourcesHook | None = None,
    ) -> VerifiedAnswer:
        """Retrieve, generate, and verify an answer with source-linked claims."""
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
        if not retrieved:
            if on_sources is not None:
                await on_sources(())
            return _uncertain_without_sources(
                requested_date,
                verifier_notes=("retrieval returned no sources",),
            )
        best_score = max(result.score for result in retrieved)
        if retrieval_score_below_tau(best_score, self._abstention_tau):
            if on_sources is not None:
                await on_sources(())
            return _uncertain_without_sources(
                requested_date,
                caveat=(
                    "De gevonden bronnen boden onvoldoende houvast voor een betrouwbaar antwoord."
                ),
                verifier_notes=(
                    f"retrieval score {best_score:.6g} is below abstention tau "
                    f"{self._abstention_tau:.6g}",
                ),
            )
        source_context, label_to_source, included_sources = self._source_context(retrieved)
        if on_sources is not None:
            await on_sources(included_sources)
        if not label_to_source:
            return _uncertain_without_sources(
                requested_date,
                verifier_notes=("no usable source text fit in the source-context budget",),
            )

        messages = self._messages(vraag.strip(), requested_date, source_context, history)
        schema = _draft_schema(tuple(label_to_source))
        draft = await self._provider.chat(
            messages,
            schema,
            False,
            ANSWER_TEMPERATURE,
        )
        if not isinstance(draft, schema):
            raise TypeError("LLMProvider returned a value outside the structured answer schema")
        draft = cast(_AnswerDraft, draft)
        if draft.peildatum != requested_date:
            actual_date = draft.peildatum.isoformat()
            expected_date = requested_date.isoformat()
            raise AnswerDateMismatchError(
                f"model returned peildatum {actual_date}, expected {expected_date}"
            )

        generated_points: list[AnswerPoint] = []
        for point in draft.punten:
            source_ids: list[UUID] = []
            for label in point.bron_ids:
                source_id = label_to_source.get(label)
                if source_id is None:
                    raise UnknownSourceLabelError(f"model cited unknown source label {label!r}")
                if source_id not in source_ids:
                    source_ids.append(source_id)
            generated_points.append(AnswerPoint(tekst=point.tekst, bron_ids=source_ids))

        source_by_id = {result.source.chunk_id: result.source for result in retrieved}
        verifier_sources = {
            source_id: CitationSource(
                chunk_id=source_id,
                text=source_by_id[source_id].tekst,
                geldig_vanaf=source_by_id[source_id].metadata.geldig_vanaf,
                geldig_tot=source_by_id[source_id].metadata.geldig_tot,
                status=source_by_id[source_id].metadata.status,
                artikel_status=source_by_id[source_id].metadata.artikel_status,
            )
            for source_id in label_to_source.values()
        }
        verification = verify_citations(
            [CitationClaim(point.tekst, tuple(point.bron_ids)) for point in generated_points],
            verifier_sources,
            requested_date,
        )
        generated_by_index = dict(enumerate(generated_points))
        verified_points = [
            AnswerPoint(
                tekst=generated_by_index[claim.point_index].tekst,
                bron_ids=list(claim.source_ids),
            )
            for claim in verification.verified_claims
        ]

        status = draft.status
        summary = draft.samenvatting
        caveats = list(draft.voorbehouden)
        followups = list(draft.vervolgstappen)
        verifier_notes = list(verification.notes)
        if verification.removed_count:
            summary = _summary_from_verified_points(verified_points)
            caveats = [_REMOVAL_CAVEAT]
            followups = []
        majority_removed = verification.strict_majority_removed
        no_verified_answered_points = status == "beantwoord" and not verified_points
        if majority_removed or no_verified_answered_points:
            status = "onzeker"
            if not verified_points:
                summary = _UNCERTAIN_SUMMARY
            if majority_removed:
                verifier_notes.append(
                    "more than half of generated points were removed; "
                    "answer status set to uncertain"
                )
            elif no_verified_answered_points:
                verifier_notes.append(
                    "no verified points remain for an answered draft; "
                    "answer status set to uncertain"
                )
        elif not verification.removed_count and status != "beantwoord":
            caveats = []
            followups = []
            if not verified_points:
                summary = _UNCERTAIN_SUMMARY if status == "onzeker" else _OUT_OF_SCOPE_SUMMARY

        return VerifiedAnswer(
            status=status,
            samenvatting=summary,
            punten=verified_points,
            voorbehouden=caveats,
            vervolgstappen=followups,
            peildatum=requested_date,
            verifier_notes=verifier_notes,
        )

    def _messages(
        self,
        vraag: str,
        peildatum: date,
        source_context: str,
        history: Sequence[ChatMessage] = (),
    ) -> list[ChatMessage]:
        bounded_history = _bound_history(history)
        user_content = (
            f"Peildatum: {peildatum.isoformat()}\n"
            f"Vraag: {vraag}\n\n"
            "Gebruik voor `bron_ids` uitsluitend de zichtbare labels uit deze BRONNEN.\n"
            "BRONNEN:\n"
            f"{source_context}"
        )
        return [
            ChatMessage(role="system", content=self._system_prompt),
            *bounded_history,
            ChatMessage(role="user", content=user_content),
        ]

    def _source_context(
        self,
        retrieved: Sequence[ScoredChunk],
    ) -> tuple[str, dict[str, UUID], tuple[IncludedAnswerSource, ...]]:
        candidates: list[SourceDocument] = []
        score_by_id: dict[UUID, float] = {}
        seen_source_ids: set[UUID] = set()
        for result in retrieved[:MAX_SOURCES]:
            source = result.source
            if source.tekst.strip() and source.chunk_id not in seen_source_ids:
                candidates.append(source)
                score_by_id[source.chunk_id] = result.score
                seen_source_ids.add(source.chunk_id)
        if not candidates:
            return "", {}, ()

        blocks: list[str] = []
        label_to_source: dict[str, UUID] = {}
        included_sources: list[IncludedAnswerSource] = []
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
            included_sources.append(
                IncludedAnswerSource(label, source, score_by_id[source.chunk_id])
            )
        return "\n\n".join(blocks), label_to_source, tuple(included_sources)

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


def _bound_history(history: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Keep a bounded suffix of user/assistant history in chronological order."""
    if any(message["role"] not in {"user", "assistant"} for message in history):
        raise ValueError("conversation history may contain only user and assistant messages")
    candidates = list(history[-MAX_HISTORY_MESSAGES:])
    selected_reversed: list[ChatMessage] = []
    remaining = MAX_HISTORY_CHARS
    for message in reversed(candidates):
        role = message["role"]
        content = message["content"].strip()
        if not content:
            continue
        if remaining <= 0:
            break
        if len(content) > remaining:
            content = content[-remaining:]
        selected_reversed.append(ChatMessage(role=role, content=content))
        remaining -= len(content)
        if len(content) < len(message["content"].strip()):
            break
    return list(reversed(selected_reversed))


def _uncertain_without_sources(
    peildatum: date,
    *,
    caveat: str = "Er zijn geen bruikbare bronnen gevonden voor deze vraag.",
    verifier_notes: Sequence[str] = (),
) -> VerifiedAnswer:
    return VerifiedAnswer(
        status="onzeker",
        samenvatting=_UNCERTAIN_SUMMARY,
        punten=[],
        voorbehouden=[caveat],
        vervolgstappen=[],
        peildatum=peildatum,
        verifier_notes=list(verifier_notes),
    )


def _summary_from_verified_points(points: Sequence[AnswerPoint]) -> str:
    selected: list[str] = []
    for point in points:
        candidate = " ".join((*selected, point.tekst.strip()))
        if len(candidate.split()) <= 80:
            selected.append(point.tekst.strip())
    return " ".join(selected) if selected else _UNCERTAIN_SUMMARY


_UNCERTAIN_SUMMARY = (
    "Ik kan deze vraag niet met voldoende zekerheid beantwoorden op basis van de gevonden bronnen."
)
_OUT_OF_SCOPE_SUMMARY = "Deze vraag valt buiten de reikwijdte van Wetvia."


__all__ = [
    "ANSWER_SEARCH_MODE",
    "ANSWER_TEMPERATURE",
    "DEFAULT_ABSTENTION_TAU",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "MAX_SOURCES",
    "MAX_SOURCE_TOKENS",
    "AnswerDateMismatchError",
    "AnswerPipeline",
    "IncludedAnswerSource",
    "IncludedSourcesHook",
    "SourceTokenCounter",
    "UnknownSourceLabelError",
    "Utf8ByteUpperBoundCounter",
]
