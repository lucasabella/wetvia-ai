"""Lazy sentence-transformers adapter for multilingual-e5 style models."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from math import isfinite, sqrt
from typing import Any, SupportsFloat, cast


class SentenceTransformersEmbedder:
    """Load a local sentence-transformers model on the best available device."""

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

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Encode formatted model input and normalize each vector to unit length."""
        if not texts:
            return []
        encoded = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        vectors = [self._normalize_vector(row) for row in encoded]
        if len(vectors) != len(texts):
            raise ValueError(
                f"model returned {len(vectors)} vectors for {len(texts)} document inputs"
            )
        return vectors

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
