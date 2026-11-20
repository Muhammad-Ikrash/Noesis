"""Slide deck design settings

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("slide_decks", sa.Column("design", JSONB()))


def downgrade() -> None:
    op.drop_column("slide_decks", "design")
