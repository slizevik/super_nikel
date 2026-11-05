"""Add full-text search index for document chunks."""

import sqlalchemy as sa
from alembic import op


revision = "0010_chunk_full_text_search"
down_revision = "0009_chunk_source_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_document_chunks_content_fts",
        "document_chunks",
        [sa.text("to_tsvector('simple', content)")],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_content_fts",
        table_name="document_chunks",
    )
