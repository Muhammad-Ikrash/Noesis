"""Quiz difficulty and question types (single choice, multiple choice, true/false)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quizzes",
        sa.Column(
            "difficulty", sa.String(10), nullable=False, server_default="medium"
        ),
    )
    op.add_column(
        "quiz_questions",
        sa.Column("kind", sa.String(20), nullable=False, server_default="single"),
    )
    op.add_column("quiz_questions", sa.Column("correct_indices", JSONB()))
    # Existing questions are single choice: their one correct option becomes a one-item list.
    op.execute(
        "UPDATE quiz_questions SET correct_indices = jsonb_build_array(correct_index)"
    )
    op.alter_column("quiz_questions", "correct_indices", nullable=False)


def downgrade() -> None:
    op.drop_column("quiz_questions", "correct_indices")
    op.drop_column("quiz_questions", "kind")
    op.drop_column("quizzes", "difficulty")
