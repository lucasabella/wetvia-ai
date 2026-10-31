"""Embedding ports and model input formatting."""

from wetvia.embeddings.formatting import format_document_input, format_query_input
from wetvia.embeddings.ports import Embedder

__all__ = ["Embedder", "format_document_input", "format_query_input"]
