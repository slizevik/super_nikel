"""Persist the single configured token budget for every ingestion job.

Revision ID: 0004_token_budget
Revises: 0003_pipeline_results
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_token_budget"
down_revision = "0003_pipeline_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_jobs",
        sa.Column(
            "token_budget_limit",
            sa.Integer(),
            server_default=sa.text("1000000"),
            nullable=False,
        ),
    )
    op.add_column(
        "ingestion_jobs",
        sa.Column(
            "tokens_consumed",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_token_budget_positive",
        "ingestion_jobs",
        "token_budget_limit > 0",
    )
    op.create_check_constraint(
        "ck_ingestion_jobs_tokens_consumed_nonnegative",
        "ingestion_jobs",
        "tokens_consumed >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ingestion_jobs_tokens_consumed_nonnegative",
        "ingestion_jobs",
        type_="check",
    )
    op.drop_constraint(
        "ck_ingestion_jobs_token_budget_positive",
        "ingestion_jobs",
        type_="check",
    )
    op.drop_column("ingestion_jobs", "tokens_consumed")
    op.drop_column("ingestion_jobs", "token_budget_limit")
