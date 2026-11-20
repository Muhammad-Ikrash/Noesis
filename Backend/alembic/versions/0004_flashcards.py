"""Flashcards

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "flashcard_decks",
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
        sa.Column("topic", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_flashcard_decks_owner_id", "flashcard_decks", ["owner_id"])
    op.create_index(
        "ix_flashcard_decks_conversation_id", "flashcard_decks", ["conversation_id"]
    )

    op.create_table(
        "flashcards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "deck_id",
            sa.Uuid(),
            sa.ForeignKey("flashcard_decks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("known", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL")
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
    )
    op.create_index("ix_flashcards_deck_id", "flashcards", ["deck_id"])


def downgrade() -> None:
    op.drop_table("flashcards")
    op.drop_table("flashcard_decks")
