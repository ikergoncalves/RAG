"""Add chunks.embedded_at to track vector-store indexing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chunks", "embedded_at")
