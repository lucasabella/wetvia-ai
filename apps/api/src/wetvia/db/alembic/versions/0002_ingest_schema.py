"""Add the BWB regulation, state and chunk schema.

Revision ID: 0002_ingest_schema
Revises: 0001_empty
Create Date: 2026-10-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002_ingest_schema"
down_revision: str | None = "0001_empty"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TSVECTOR_EXPRESSION = """
to_tsvector(
    'dutch',
    coalesce(regeling_titel, '') || ' ' || coalesce(artikel, '') || ' ' ||
    coalesce(lid, '') || ' ' || coalesce(onderdeel, '') || ' ' ||
    coalesce(opschrift, '') || ' ' || coalesce(kop_pad, '') || ' ' || coalesce(tekst, '')
)
""".strip()


def upgrade() -> None:
    """Create the Postgres/pgvector schema; SQLite is used only for env tests."""
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        return
    if dialect_name != "postgresql":
        raise RuntimeError("the Wetvia ingest schema requires PostgreSQL and pgvector")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "regeling",
        sa.Column("bwb_id", sa.String(length=16), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("bwb_id"),
    )
    op.create_table(
        "toestand",
        sa.Column("toestand_url", sa.String(length=2048), nullable=False),
        sa.Column("bwb_id", sa.String(length=16), nullable=False),
        sa.Column("geldig_vanaf", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column("modified", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["bwb_id"], ["regeling.bwb_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("toestand_url"),
    )
    op.create_index("ix_toestand_bwb_id", "toestand", ["bwb_id"])
    op.create_index("ix_toestand_validity", "toestand", ["geldig_vanaf", "geldig_tot"])

    op.create_table(
        "chunk",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("toestand_url", sa.String(length=2048), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("bwb_id", sa.String(length=16), nullable=False),
        sa.Column("regeling_titel", sa.Text(), nullable=False),
        sa.Column("artikel", sa.String(length=80), nullable=False),
        sa.Column("lid", sa.String(length=40), nullable=True),
        sa.Column("onderdeel", sa.String(length=160), nullable=True),
        sa.Column("opschrift", sa.Text(), nullable=True),
        sa.Column("kop_pad", sa.Text(), nullable=False),
        sa.Column("tekst", sa.Text(), nullable=False),
        sa.Column("geldig_vanaf", sa.Date(), nullable=False),
        sa.Column("geldig_tot", sa.Date(), nullable=True),
        sa.Column("bron_url", sa.String(length=2048), nullable=False),
        sa.Column("artikel_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(_TSVECTOR_EXPRESSION, persisted=True),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunk_index_nonnegative"),
        sa.CheckConstraint(
            "artikel_status IN ('geldend', 'vervallen')", name="ck_chunk_article_status"
        ),
        sa.CheckConstraint(
            "status IN ('geldend', 'toekomstig', 'vervallen')", name="ck_chunk_status"
        ),
        sa.ForeignKeyConstraint(["bwb_id"], ["regeling.bwb_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["toestand_url"], ["toestand.toestand_url"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("toestand_url", "chunk_index", name="uq_chunk_toestand_index"),
    )
    op.create_index("ix_chunk_tsv_gin", "chunk", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_chunk_validity", "chunk", ["geldig_vanaf", "geldig_tot"])
    op.create_index("ix_chunk_bwb_article", "chunk", ["bwb_id", "artikel"])


def downgrade() -> None:
    """Remove the ingestion-owned tables without removing the shared extension."""
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        return
    if dialect_name != "postgresql":
        raise RuntimeError("the Wetvia ingest schema requires PostgreSQL and pgvector")

    op.drop_table("chunk")
    op.drop_index("ix_toestand_validity", table_name="toestand")
    op.drop_index("ix_toestand_bwb_id", table_name="toestand")
    op.drop_table("toestand")
    op.drop_table("regeling")
