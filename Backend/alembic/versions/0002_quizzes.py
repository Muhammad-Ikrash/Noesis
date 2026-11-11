"""Quizzes

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quizzes",
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
    op.create_index("ix_quizzes_owner_id", "quizzes", ["owner_id"])
    op.create_index("ix_quizzes_conversation_id", "quizzes", ["conversation_id"])

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.Uuid(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", JSONB(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
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
    op.create_index("ix_quiz_questions_quiz_id", "quiz_questions", ["quiz_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "quiz_id",
            sa.Uuid(),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("answers", JSONB(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])


def downgrade() -> None:
    op.drop_table("quiz_attempts")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
