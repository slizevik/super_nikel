"""PostgreSQL full-text retrieval over indexed document chunks."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal_column, select

from app.db.models import Document, DocumentChunk, IngestionJob
from app.services.query_expansion import build_expanded_tsquery


@dataclass(frozen=True)
class FullTextChunkResult:
    document_id: UUID
    chunk_id: UUID
    original_filename: str
    library_relative_path: str | None
    content: str
    excerpt: str
    score: float
    page_start: int | None
    page_end: int | None
    heading: str | None


def build_full_text_queries(
    query: str,
    translated_query: str | None = None,
) -> tuple[object, object, object]:
    text_config = literal_column("'simple'")
    original_query = func.websearch_to_tsquery(text_config, query)
    translated = translated_query or query
    translated_tsquery = func.websearch_to_tsquery(text_config, translated)
    expanded_text = build_expanded_tsquery(translated)
    expanded_query = (
        func.to_tsquery(text_config, expanded_text)
        if expanded_text
        else translated_tsquery
    )
    return original_query, translated_tsquery, expanded_query


def search_chunks_full_text(
    session,
    query: str,
    *,
    translated_query: str | None = None,
    limit: int = 8,
) -> list[FullTextChunkResult]:
    if not query.strip():
        return []
    if limit <= 0:
        raise ValueError("Search limit must be positive.")

    original_query, translated_tsquery, expanded_query = build_full_text_queries(
        query,
        translated_query,
    )
    text_config = literal_column("'simple'")
    search_vector = func.to_tsvector(text_config, DocumentChunk.content)
    score = (
        func.ts_rank(search_vector, original_query)
        + func.ts_rank(search_vector, translated_tsquery)
        + func.ts_rank(search_vector, expanded_query)
    )
    matching_job = select(IngestionJob.id).where(
        IngestionJob.document_id == DocumentChunk.document_id,
        IngestionJob.status == "completed",
    ).exists()
    rows = session.execute(
        select(
            Document.id,
            DocumentChunk.id,
            Document.original_filename,
            Document.library_relative_path,
            DocumentChunk.content,
            func.ts_headline(
                text_config,
                DocumentChunk.content,
                expanded_query,
                "MaxWords=120, MinWords=30, MaxFragments=3, "
                "FragmentDelimiter=' ... '",
            ),
            score,
            DocumentChunk.page_start,
            DocumentChunk.page_end,
            DocumentChunk.heading,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.source_type == "library",
            matching_job,
            search_vector.bool_op("@@")(original_query)
            | search_vector.bool_op("@@")(translated_tsquery)
            | search_vector.bool_op("@@")(expanded_query),
        )
        .order_by(score.desc())
        .limit(limit)
    ).all()
    return [
        FullTextChunkResult(
            document_id=document_id,
            chunk_id=chunk_id,
            original_filename=filename,
            library_relative_path=relative_path,
            content=content,
            excerpt=excerpt,
            score=float(rank),
            page_start=page_start,
            page_end=page_end,
            heading=heading,
        )
        for (
            document_id,
            chunk_id,
            filename,
            relative_path,
            content,
            excerpt,
            rank,
            page_start,
            page_end,
            heading,
        ) in rows
        if excerpt and excerpt.strip()
    ]
