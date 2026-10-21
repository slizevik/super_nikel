"""Support documents indexed from a read-only local library."""

from alembic import op
import sqlalchemy as sa


revision = "0006_library_documents"
down_revision = "0005_document_docx_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "source_type",
            sa.String(length=20),
            server_default=sa.text("'upload'"),
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("library_relative_path", sa.String(length=1024), nullable=True),
    )
    op.alter_column("documents", "original_file", nullable=True)
    op.create_unique_constraint(
        "uq_documents_library_relative_path",
        "documents",
        ["library_relative_path"],
    )
    op.create_check_constraint(
        "ck_documents_source_storage",
        "documents",
        "(source_type = 'upload' AND original_file IS NOT NULL "
        "AND library_relative_path IS NULL) OR "
        "(source_type = 'library' AND original_file IS NULL "
        "AND library_relative_path IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_documents_source_storage",
        "documents",
        type_="check",
    )
    op.drop_constraint(
        "uq_documents_library_relative_path",
        "documents",
        type_="unique",
    )
    op.alter_column("documents", "original_file", nullable=False)
    op.drop_column("documents", "library_relative_path")
    op.drop_column("documents", "source_type")
