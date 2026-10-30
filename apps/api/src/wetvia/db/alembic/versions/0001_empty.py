"""empty initial schema

Revision ID: 0001_empty
Revises:
Create Date: 2026-10-30

"""

from collections.abc import Sequence

revision: str = "0001_empty"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No tables yet. Later modules add their own revisions."""


def downgrade() -> None:
    """Nothing to undo."""
