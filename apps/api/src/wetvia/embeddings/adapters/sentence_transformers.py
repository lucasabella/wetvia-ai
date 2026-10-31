"""Lazy sentence-transformers adapter for multilingual-e5 style models."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, SupportsFloat, cast

_OVERLAP_TOKENS = 32


@dataclass(frozen=True, slots=True)
class _InputWindow:
    text: str
    token_count: int


class SentenceTransformersEmbedder:
    """Load a local model and cover long input with overlapping token windows."""

    def __init__(
        self,
        model_name: str,
        *,
        dimension: int,
        model: Any | None = None,
        torch_module: Any | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        torch = torch_module if torch_module is not None else _load_torch()
        self.device = _select_device(torch)
        self.dtype = torch.float16 if self.device in {"cuda", "mps"} else torch.float32

        if model is None:
            sentence_transformers = _load_sentence_transformers()
            model = sentence_transformers.SentenceTransformer(
                model_name,
                device=self.device,
                model_kwargs={"torch_dtype": self.dtype},
            )

        actual_dimension = model.get_sentence_embedding_dimension()
        if actual_dimension != dimension:
            raise ValueError(
                f"model {model_name!r} returns {actual_dimension} dimensions; "
                f"configured dimension is {dimension}"
            )
        self._model = model
        self.model_id = model_name
        self.dimension = dimension
        self._tokenizer = _model_tokenizer(model)
        max_seq_length = getattr(model, "max_seq_length", None)
        if not isinstance(max_seq_length, int) or max_seq_length <= 0:
            raise ValueError("sentence-transformers model must expose a positive max_seq_length")
        self._max_seq_length = max_seq_length
        count_special = getattr(self._tokenizer, "num_special_tokens_to_add", None)
        self._special_tokens = int(count_special(pair=False)) if callable(count_special) else 2
        if self._max_seq_length <= self._special_tokens:
            raise ValueError("model max_seq_length leaves no room for input tokens")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode every input window and aggregate them into one unit vector per input."""
        if not texts:
            return []
        windows_by_input = [self._split_input(text) for text in texts]
        windows = [window for group in windows_by_input for window in group]
        encoded = self._model.encode(
            [window.text for window in windows],
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        window_vectors = [self._normalize_vector(row) for row in encoded]
        if len(window_vectors) != len(windows):
            raise ValueError(
                f"model returned {len(window_vectors)} vectors for {len(windows)} input windows"
            )
        vectors: list[list[float]] = []
        offset = 0
        for group in windows_by_input:
            group_vectors = window_vectors[offset : offset + len(group)]
            offset += len(group)
            total_weight = sum(window.token_count for window in group) or len(group)
            aggregate = [
                sum(
                    vector[index] * (window.token_count or 1)
                    for window, vector in zip(group, group_vectors, strict=True)
                )
                / total_weight
                for index in range(self.dimension)
            ]
            vectors.append(self._normalize_vector(aggregate))
        return vectors

    def _split_input(self, text: str) -> list[_InputWindow]:
        max_content_tokens = self._max_seq_length - self._special_tokens
        token_ids, _ = self._tokenize(text)
        if len(token_ids) <= max_content_tokens:
            return [_InputWindow(text, len(token_ids))]

        # The first line contains regulation/article context. Repeating it keeps
        # that legal provenance attached to each body window when space allows.
        heading, separator, body = text.partition("\n")
        if separator and body:
            heading_tokens, _ = self._tokenize(heading)
            body_budget = max_content_tokens - len(heading_tokens) - 1 - 2
            if body_budget >= 2:
                body_windows = self._split_text(body, body_budget)
                contextual = [
                    _InputWindow(f"{heading}{separator}{window.text}", window.token_count)
                    for window in body_windows
                ]
                if all(
                    len(self._tokenize(window.text)[0]) <= max_content_tokens
                    for window in contextual
                ):
                    return contextual
        return self._split_text(text, max_content_tokens)

    def _split_text(self, text: str, max_tokens: int) -> list[_InputWindow]:
        token_ids, offsets = self._tokenize(text)
        if len(token_ids) <= max_tokens:
            return [_InputWindow(text, len(token_ids))]

        if offsets is None:
            return self._split_token_ids(text, token_ids, max_tokens)

        overlap = min(_OVERLAP_TOKENS, max(1, max_tokens // 8))
        windows: list[_InputWindow] = []
        start = 0
        while start < len(token_ids):
            end = min(start + max_tokens, len(token_ids))
            if end < len(token_ids):
                end = _prefer_unit_boundary(text, offsets, start, end)
            char_start = 0 if start == 0 else offsets[start][0]
            char_end = len(text) if end == len(token_ids) else offsets[end - 1][1]
            windows.append(_InputWindow(text[char_start:char_end], end - start))
            if end == len(token_ids):
                break
            start = max(start + 1, end - overlap)
        return windows

    def _split_token_ids(
        self, text: str, token_ids: list[int], max_tokens: int
    ) -> list[_InputWindow]:
        decode = getattr(self._tokenizer, "decode", None)
        if not callable(decode):
            raise RuntimeError(
                "tokenizer must support offsets or token decoding to cover long input"
            )
        window_size = max(1, max_tokens - 2)
        overlap = min(_OVERLAP_TOKENS, max(1, window_size // 8))
        windows: list[_InputWindow] = []
        start = 0
        while start < len(token_ids):
            end = min(start + window_size, len(token_ids))
            ids = token_ids[start:end]
            try:
                decoded = decode(
                    ids,
                    skip_special_tokens=True,
                    clean_up_tokenization_spaces=False,
                )
            except TypeError:
                decoded = decode(ids, skip_special_tokens=True)
            windows.append(_InputWindow(str(decoded), len(ids)))
            if end == len(token_ids):
                break
            start = max(start + 1, end - overlap)
        if not windows and text:
            raise RuntimeError("tokenizer produced no windows for non-empty input")
        return windows

    def _tokenize(self, text: str) -> tuple[list[int], list[tuple[int, int]] | None]:
        try:
            encoded = self._tokenizer(
                text,
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False,
            )
            token_ids = _flatten_ids(encoded["input_ids"])
            offsets = _flatten_offsets(encoded.get("offset_mapping"))
            if offsets is not None and len(offsets) == len(token_ids):
                return token_ids, offsets
        except (AttributeError, KeyError, NotImplementedError, TypeError, ValueError):
            pass
        token_ids = _flatten_ids(self._tokenizer.encode(text, add_special_tokens=False))
        return token_ids, None

    def _normalize_vector(self, values: Sequence[object]) -> list[float]:
        vector = [float(cast(SupportsFloat, value)) for value in values]
        if len(vector) != self.dimension:
            raise ValueError(
                f"model returned a {len(vector)}-dimension vector; expected {self.dimension}"
            )
        if not all(isfinite(value) for value in vector):
            raise ValueError("model returned a vector containing a non-finite value")
        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise ValueError("model returned a zero-length vector")
        return [value / norm for value in vector]


def _select_device(torch: Any) -> str:
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


def _model_tokenizer(model: Any) -> Any:
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        try:
            tokenizer = model[0].tokenizer
        except (IndexError, KeyError, TypeError):
            tokenizer = None
    if tokenizer is None:
        raise ValueError("sentence-transformers model must expose its tokenizer")
    return tokenizer


def _flatten_ids(values: Any) -> list[int]:
    if values and isinstance(values[0], (list, tuple)):
        if len(values) != 1:
            raise ValueError("tokenizer returned a batch for one input")
        values = values[0]
    return [int(value) for value in values]


def _flatten_offsets(values: Any) -> list[tuple[int, int]] | None:
    if values is None:
        return None
    if (
        values
        and isinstance(values[0], (list, tuple))
        and values[0]
        and isinstance(values[0][0], (list, tuple))
    ):
        if len(values) != 1:
            raise ValueError("tokenizer returned offset batches for one input")
        values = values[0]
    return [(int(start), int(end)) for start, end in values]


def _prefer_unit_boundary(
    text: str,
    offsets: Sequence[tuple[int, int]],
    start: int,
    end: int,
) -> int:
    earliest = start + max(1, (end - start) // 2)
    for boundary in range(end, earliest, -1):
        char_end = offsets[boundary - 1][1]
        next_start = offsets[boundary][0]
        previous = text[char_end - 1] if char_end > 0 else ""
        separator = text[char_end:next_start]
        if previous in ".;:!?" or "\n" in separator:
            return boundary
    for boundary in range(end, earliest, -1):
        char_end = offsets[boundary - 1][1]
        next_start = offsets[boundary][0]
        previous = text[char_end - 1] if char_end > 0 else ""
        separator = text[char_end:next_start]
        if previous.isspace() or any(char.isspace() for char in separator):
            return boundary
    return end


def _load_torch() -> Any:
    try:
        return importlib.import_module("torch")
    except ImportError as exc:
        raise RuntimeError(
            "embedding inference needs the optional extra: uv sync --extra embeddings"
        ) from exc


def _load_sentence_transformers() -> Any:
    try:
        return importlib.import_module("sentence_transformers")
    except ImportError as exc:
        raise RuntimeError(
            "embedding inference needs the optional extra: uv sync --extra embeddings"
        ) from exc
