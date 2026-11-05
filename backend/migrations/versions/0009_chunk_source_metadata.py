"""Add source location metadata to document chunks."""

from alembic import op
import sqlalchemy as sa


revision = "0009_chunk_source_metadata"
down_revision = "0008_persistent_chat_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column("page_start", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("page_end", sa.Integer(), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("heading", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "heading")
    op.drop_column("document_chunks", "page_end")
    op.drop_column("document_chunks", "page_start")
