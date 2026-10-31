"""PostgreSQL tables written by ``wetvia.ingest``."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from wetvia.db.base import Base

_TSVECTOR_EXPRESSION = """
to_tsvector(
    'dutch',
    coalesce(regeling_titel, '') || ' ' || coalesce(artikel, '') || ' ' ||
    coalesce(lid, '') || ' ' || coalesce(onderdeel, '') || ' ' ||
    coalesce(opschrift, '') || ' ' || coalesce(kop_pad, '') || ' ' || coalesce(tekst, '')
)
""".strip()


class RegelingRecord(Base):
    """One official BWB regulation."""

    __tablename__ = "regeling"

    bwb_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    titel: Mapped[str] = mapped_column(Text, nullable=False)


class ToestandRecord(Base):
    """Official validity metadata for one version of a regulation."""

    __tablename__ = "toestand"

    toestand_url: Mapped[str] = mapped_column(String(2048), primary_key=True)
    bwb_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("regeling.bwb_id", ondelete="CASCADE"), nullable=False
    )
    geldig_vanaf: Mapped[date] = mapped_column(Date, nullable=False)
    geldig_tot: Mapped[date | None] = mapped_column(Date, nullable=True)
    modified: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        Index("ix_toestand_bwb_id", "bwb_id"),
        Index("ix_toestand_validity", "geldig_vanaf", "geldig_tot"),
    )


class ChunkRecord(Base):
    """A parsed legal text chunk with provenance and retrieval columns."""

    __tablename__ = "chunk"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    toestand_url: Mapped[str] = mapped_column(
        String(2048), ForeignKey("toestand.toestand_url", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    bwb_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("regeling.bwb_id", ondelete="CASCADE"), nullable=False
    )
    regeling_titel: Mapped[str] = mapped_column(Text, nullable=False)
    artikel: Mapped[str] = mapped_column(String(80), nullable=False)
    lid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    onderdeel: Mapped[str | None] = mapped_column(String(160), nullable=True)
    opschrift: Mapped[str | None] = mapped_column(Text, nullable=True)
    kop_pad: Mapped[str] = mapped_column(Text, nullable=False)
    tekst: Mapped[str] = mapped_column(Text, nullable=False)
    geldig_vanaf: Mapped[date] = mapped_column(Date, nullable=False)
    geldig_tot: Mapped[date | None] = mapped_column(Date, nullable=True)
    bron_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    artikel_status: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(_TSVECTOR_EXPRESSION, persisted=True),
        nullable=False,
    )
    # Alembic constrains the physical PostgreSQL width; the job reads that width
    # at runtime so later vector-dimension migrations need no ORM code edit.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)

    __table_args__ = (
        UniqueConstraint("toestand_url", "chunk_index", name="uq_chunk_toestand_index"),
        CheckConstraint("chunk_index >= 0", name="ck_chunk_index_nonnegative"),
        CheckConstraint(
            "artikel_status IN ('geldend', 'vervallen')",
            name="ck_chunk_article_status",
        ),
        CheckConstraint(
            "status IN ('geldend', 'toekomstig', 'vervallen')",
            name="ck_chunk_status",
        ),
        Index("ix_chunk_tsv_gin", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunk_validity", "geldig_vanaf", "geldig_tot"),
        Index("ix_chunk_bwb_article", "bwb_id", "artikel"),
    )
