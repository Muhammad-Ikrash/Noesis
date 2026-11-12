"""Ingestion progress

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("progress_done", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("progress_total", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "progress_total")
    op.drop_column("documents", "progress_done")
