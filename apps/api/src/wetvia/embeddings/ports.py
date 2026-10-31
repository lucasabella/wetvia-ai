"""Public ports for local or remote embedding adapters."""

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    """Encode batches of already formatted model input text into vectors."""

    @property
    def model_id(self) -> str:
        """Stable identifier of the vector space used by this adapter."""

    @property
    def dimension(self) -> int:
        """Number of float values returned for each input."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one normalized vector per formatted input, preserving order."""
