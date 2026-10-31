"""Track the single model space used for stored chunk embeddings.

Revision ID: 0003_embedding_config
Revises: 0002_ingest_schema
Create Date: 2026-10-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_embedding_config"
down_revision: str | None = "0002_ingest_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the singleton embedding model identity table on PostgreSQL."""
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        return
    if dialect_name != "postgresql":
        raise RuntimeError("the Wetvia embedding schema requires PostgreSQL and pgvector")

    op.create_table(
        "embedding_config",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("model_id", sa.String(length=512), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_embedding_config_singleton"),
        sa.CheckConstraint("dimension > 0", name="ck_embedding_config_dimension_positive"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop embedding model identity metadata."""
    dialect_name = op.get_bind().dialect.name
    if dialect_name == "sqlite":
        return
    if dialect_name != "postgresql":
        raise RuntimeError("the Wetvia embedding schema requires PostgreSQL and pgvector")
    op.drop_table("embedding_config")
