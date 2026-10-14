"""Allow DOCX source documents alongside PDFs."""

from alembic import op


revision = "0005_document_docx_support"
down_revision = "0004_token_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_pdf_only", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_supported_formats",
        "documents",
        "mime_type IN ("
        "'application/pdf', "
        "'application/vnd.openxmlformats-officedocument.wordprocessingml.document'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_documents_supported_formats",
        "documents",
        type_="check",
    )
    op.create_check_constraint(
        "ck_documents_pdf_only",
        "documents",
        "mime_type = 'application/pdf'",
    )
