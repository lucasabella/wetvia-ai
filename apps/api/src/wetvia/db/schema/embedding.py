"""Active embedding-space identity used to prevent mixed model vectors."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from wetvia.db.base import Base


class EmbeddingConfigRecord(Base):
    """Singleton model identity for all non-NULL chunk vectors."""

    __tablename__ = "embedding_config"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    model_id: Mapped[str] = mapped_column(String(512), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_embedding_config_singleton"),
        CheckConstraint("dimension > 0", name="ck_embedding_config_dimension_positive"),
    )
