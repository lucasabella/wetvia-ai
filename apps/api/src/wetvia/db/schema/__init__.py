"""Database schema models owned by feature modules."""

from wetvia.db.schema.embedding import EmbeddingConfigRecord
from wetvia.db.schema.ingest import ChunkRecord, RegelingRecord, ToestandRecord

__all__ = [
    "ChunkRecord",
    "EmbeddingConfigRecord",
    "RegelingRecord",
    "ToestandRecord",
]
