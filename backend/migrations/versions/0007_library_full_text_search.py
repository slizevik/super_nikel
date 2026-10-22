"""Add full-text search index for indexed library documents."""

import sqlalchemy as sa
from alembic import op


revision = "0007_library_full_text_search"
down_revision = "0006_library_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ingestion_jobs_extracted_text_fts",
        "ingestion_jobs",
        [sa.text("to_tsvector('simple', COALESCE(extracted_text, ''))")],
        unique=False,
        postgresql_using="gin",
        postgresql_where="status = 'completed' AND extracted_text IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ingestion_jobs_extracted_text_fts",
        table_name="ingestion_jobs",
    )
