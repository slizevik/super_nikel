from pgvector.sqlalchemy import Vector

from app.db.base import Base
from app.db.models import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    IngestionJob,
)


def test_document_storage_supports_pdf_and_docx() -> None:
    table = Document.__table__

    assert {"original_file", "sha256", "category", "source_metadata"} <= set(
        table.columns.keys()
    )
    assert {
        "source_type",
        "library_relative_path",
    } <= set(table.columns.keys())
    assert table.columns["original_file"].nullable
    format_constraint = next(
        check
        for check in table.constraints
        if getattr(check, "name", None) == "ck_documents_supported_formats"
    )
    assert "application/pdf" in str(format_constraint.sqltext)
    assert (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        in str(format_constraint.sqltext)
    )


def test_ingestion_job_has_bounded_status_and_progress() -> None:
    table = IngestionJob.__table__

    assert "document_id" in table.columns
    assert any(
        "queued" in str(check.sqltext)
        and "processing" in str(check.sqltext)
        and "awaiting_persistence" in str(check.sqltext)
        and "awaiting_extraction" not in str(check.sqltext)
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
    assert {"token_budget_limit", "tokens_consumed"} <= set(table.columns.keys())


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
    assert any(
        index.name == "ix_document_chunks_content_fts" for index in table.indexes
    )


def test_chunks_have_source_location_metadata() -> None:
    table = DocumentChunk.__table__

    assert {"page_start", "page_end", "heading", "metadata"} <= set(
        table.columns.keys()
    )
    assert table.columns["page_start"].nullable
    assert table.columns["page_end"].nullable
    assert table.columns["heading"].nullable
    assert table.columns["metadata"].nullable is False


def test_all_models_are_registered_for_migrations() -> None:
    assert set(Base.metadata.tables) == {
        "documents",
        "ingestion_jobs",
        "document_chunks",
        "chat_sessions",
        "chat_messages",
    }


def test_chat_messages_are_persisted_with_citations_and_cascade() -> None:
    session_table = ChatSession.__table__
    message_table = ChatMessage.__table__

    assert {"title", "created_at", "updated_at"} <= set(session_table.columns.keys())
    assert {
        "chat_id",
        "question",
        "answer",
        "translated_question",
        "citations",
    } <= set(message_table.columns.keys())
    foreign_key = next(iter(message_table.foreign_keys))
    assert foreign_key.target_fullname == "chat_sessions.id"
    assert foreign_key.ondelete == "CASCADE"
    assert any(
        index.name == "ix_chat_messages_chat_created_at"
        for index in message_table.indexes
    )
