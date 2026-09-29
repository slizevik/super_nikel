from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.db.models import Document, DocumentChunk, IngestionJob


def test_document_storage_and_pdf_only_constraint() -> None:
    table = Document.__table__

    assert {"original_file", "sha256", "category", "source_metadata"} <= set(
        table.columns.keys()
    )
    assert any(
        "mime_type = 'application/pdf'" in str(check.sqltext)
        for check in table.constraints
        if hasattr(check, "sqltext")
    )


def test_ingestion_job_has_bounded_status_and_progress() -> None:
    table = IngestionJob.__table__

    assert "document_id" in table.columns
    assert any(
        "queued" in str(check.sqltext)
        and "processing" in str(check.sqltext)
        and "completed" in str(check.sqltext)
        and "failed" in str(check.sqltext)
        for check in table.constraints
        if hasattr(check, "sqltext")
    )
    assert any(
        "progress_percent BETWEEN 0 AND 100" in str(check.sqltext)
        for check in table.constraints
        if hasattr(check, "sqltext")
    )


def test_chunks_have_e5_vectors_and_search_indexes() -> None:
    table = DocumentChunk.__table__
    embedding_type = table.columns["embedding"].type

    assert isinstance(embedding_type, Vector)
    assert embedding_type.dim == 1024
    assert any(
        index.name == "ix_document_chunks_embedding_cosine"
        for index in table.indexes
    )
    assert any(index.name == "ix_document_chunks_metadata" for index in table.indexes)


def test_all_models_are_registered_for_migrations() -> None:
    assert set(Base.metadata.tables) == {
        "documents",
        "ingestion_jobs",
        "document_chunks",
    }
