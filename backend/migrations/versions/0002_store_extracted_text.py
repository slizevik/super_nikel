"""Store extracted document text and represent the pending LLM stage.

Revision ID: 0002_extracted_text
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_extracted_text"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_jobs", sa.Column("extracted_text", sa.Text()))
    op.drop_constraint(
        "ck_ingestion_jobs_status", "ingestion_jobs", type_="check"
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_status",
        "ingestion_jobs",
        "status IN ('queued', 'processing', 'awaiting_extraction', 'completed', 'failed')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE ingestion_jobs SET status = 'processing' "
        "WHERE status = 'awaiting_extraction'"
    )
    op.drop_constraint(
        "ck_ingestion_jobs_status", "ingestion_jobs", type_="check"
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_status",
        "ingestion_jobs",
        "status IN ('queued', 'processing', 'completed', 'failed')",
    )
    op.drop_column("ingestion_jobs", "extracted_text")
