"""Initial schema with pgvector

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSION = 1024


def _enum(name: str, *values: str) -> pg.ENUM:
    return pg.ENUM(*values, name=name, create_type=False)


ENUMS = {
    "retrieval_scope": ("session", "library"),
    "document_status": ("pending", "processing", "completed", "failed", "missing"),
    "page_extraction": ("text", "ocr"),
    "chunk_kind": ("text", "table"),
    "learning_mode": ("basic", "extensive"),
    "message_role": ("user", "assistant"),
    "answer_status": (
        "answered",
        "insufficient_context",
        "needs_clarification",
        "error",
    ),
}


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for name, values in ENUMS.items():
        pg.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255)),
        sa.Column(
            "default_retrieval_scope",
            _enum("retrieval_scope", *ENUMS["retrieval_scope"]),
            nullable=False,
        ),
        _ts("created_at"),
        _ts("updated_at"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(128), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column(
            "status",
            _enum("document_status", *ENUMS["document_status"]),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("embedding_model", sa.String(255)),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("owner_id", "sha256", name="uq_documents_owner_sha256"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    op.create_table(
        "document_pages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("table_count", sa.Integer(), nullable=False),
        sa.Column("needs_ocr", sa.Boolean(), nullable=False),
        sa.Column(
            "extraction_method",
            _enum("page_extraction", *ENUMS["page_extraction"]),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id", "page_number", name="uq_document_pages_document_id"
        ),
        sa.CheckConstraint("page_number >= 1", name="page_number_positive"),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("kind", _enum("chunk_kind", *ENUMS["chunk_kind"]), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        _ts("created_at"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id"
        ),
        sa.CheckConstraint("page_number >= 1", name="page_number_positive"),
    )
    op.create_index(
        "ix_document_chunks_document_id", "document_chunks", ["document_id"]
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "mode", _enum("learning_mode", *ENUMS["learning_mode"]), nullable=False
        ),
        sa.Column(
            "retrieval_scope",
            _enum("retrieval_scope", *ENUMS["retrieval_scope"]),
            nullable=False,
        ),
        _ts("last_message_at", nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])

    op.create_table(
        "conversation_documents",
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "document_id",
            sa.Uuid(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        _ts("attached_at", nullable=True),
    )
    op.create_index(
        "ix_conversation_documents_document_id",
        "conversation_documents",
        ["document_id"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role", _enum("message_role", *ENUMS["message_role"]), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("supplementary", sa.Text()),
        sa.Column(
            "mode", _enum("learning_mode", *ENUMS["learning_mode"]), nullable=False
        ),
        sa.Column(
            "retrieval_scope", _enum("retrieval_scope", *ENUMS["retrieval_scope"])
        ),
        sa.Column("answer_status", _enum("answer_status", *ENUMS["answer_status"])),
        sa.Column("needs_clarification", sa.Boolean(), nullable=False),
        sa.Column("clarification_question", sa.Text()),
        _ts("created_at"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "message_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id",
            sa.Uuid(),
            sa.ForeignKey("document_chunks.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="SET NULL")
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text()),
        sa.Column("score", sa.Float()),
    )
    for col in ("message_id", "chunk_id", "document_id"):
        op.create_index(f"ix_message_sources_{col}", "message_sources", [col])


def downgrade() -> None:
    for table in (
        "message_sources",
        "messages",
        "conversation_documents",
        "conversations",
        "document_chunks",
        "document_pages",
        "documents",
        "users",
    ):
        op.drop_table(table)
    for name in ENUMS:
        pg.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
