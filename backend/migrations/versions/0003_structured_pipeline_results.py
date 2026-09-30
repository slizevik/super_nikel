"""Store structured Docling and extraction results.

Revision ID: 0003_pipeline_results
Revises: 0002_extracted_text
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_pipeline_results"
down_revision = "0002_extracted_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column("document_manifest", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("image_descriptions", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column("extraction_result", postgresql.JSONB(), nullable=True),
    )
    op.execute(
        "UPDATE ingestion_jobs "
        "SET status = 'failed', current_step = 'llm_configuration', "
        "error_code = 'LLM_CREDENTIALS_MISSING', "
        "error_message = 'LLM credentials are required to extract entities.', "
        "finished_at = now() "
        "WHERE status = 'awaiting_extraction'"
    )
    op.drop_constraint("ck_ingestion_jobs_status", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_status",
        "ingestion_jobs",
        "status IN ('queued', 'processing', 'awaiting_persistence', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ingestion_jobs SET status = 'processing' "
        "WHERE status = 'awaiting_persistence'"
    )
    op.drop_constraint("ck_ingestion_jobs_status", "ingestion_jobs", type_="check")
    op.create_check_constraint(
        "ck_ingestion_jobs_status",
        "ingestion_jobs",
        "status IN ('queued', 'processing', 'completed', 'failed')",
    )
    op.drop_column("ingestion_jobs", "extraction_result")
    op.drop_column("ingestion_jobs", "image_descriptions")
    op.drop_column("ingestion_jobs", "document_manifest")
