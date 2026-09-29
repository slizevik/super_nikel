"""Create document ingestion and vector search schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(length=127),
            server_default=sa.text("'application/pdf'"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column(
            "authors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_file", sa.LargeBinary(), nullable=False),
        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "file_size_bytes > 0", name="ck_documents_file_size_positive"
        ),
        sa.CheckConstraint(
            "mime_type = 'application/pdf'", name="ck_documents_pdf_only"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("current_step", sa.String(length=100), nullable=True),
        sa.Column(
            "progress_percent",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_ingestion_jobs_status",
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_ingestion_jobs_progress_range",
        ),
        sa.CheckConstraint("attempt >= 0", name="ck_ingestion_jobs_attempt_nonnegative"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_ingestion_jobs_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ingestion_jobs"),
        sa.UniqueConstraint("celery_task_id", name="uq_ingestion_jobs_celery_task_id"),
    )
    op.create_index(
        "ix_ingestion_jobs_status_created_at",
        "ingestion_jobs",
        ["status", "created_at"],
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "embedding", Vector(1024), nullable=False
        ),
        sa.Column(
            "embedding_model",
            sa.String(length=255),
            server_default=sa.text("'intfloat/multilingual-e5-large'"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0", name="ck_document_chunks_index_nonnegative"
        ),
        sa.CheckConstraint(
            "token_count > 0", name="ck_document_chunks_token_count_positive"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_chunks_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_index"
        ),
    )
    op.create_index(
        "ix_document_chunks_embedding_cosine",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
    )
    op.create_index(
        "ix_document_chunks_metadata",
        "document_chunks",
        ["metadata"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_metadata", table_name="document_chunks")
    op.drop_index("ix_document_chunks_embedding_cosine", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(
        "ix_ingestion_jobs_status_created_at", table_name="ingestion_jobs"
    )
    op.drop_table("ingestion_jobs")
    op.drop_table("documents")
    op.execute("DROP EXTENSION IF EXISTS vector")
