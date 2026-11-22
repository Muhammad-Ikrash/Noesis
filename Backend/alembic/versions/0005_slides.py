"""Slide decks

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "slide_decks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(500)),
        sa.Column("topic", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_slide_decks_owner_id", "slide_decks", ["owner_id"])
    op.create_index(
        "ix_slide_decks_conversation_id", "slide_decks", ["conversation_id"]
    )

    op.create_table(
        "slides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deck_id",
            sa.Uuid(),
            sa.ForeignKey("slide_decks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("bullets", JSONB(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("sources", JSONB(), nullable=False),
    )
    op.create_index("ix_slides_deck_id", "slides", ["deck_id"])


def downgrade() -> None:
    op.drop_table("slides")
    op.drop_table("slide_decks")
