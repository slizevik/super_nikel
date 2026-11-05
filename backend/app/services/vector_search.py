"""Cosine-similarity retrieval over document chunk embeddings."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import literal, select

from app.db.models import Document, DocumentChunk, IngestionJob
from app.services.embeddings import EmbeddingProvider, validate_embedding


@dataclass(frozen=True)
class VectorChunkResult:
    document_id: UUID
    chunk_id: UUID
    original_filename: str
    library_relative_path: str | None
    content: str
    similarity: float
    page_start: int | None
    page_end: int | None
    heading: str | None


def search_chunks_vector(
    session,
    query: str,
    provider: EmbeddingProvider,
    *,
    limit: int = 8,
) -> list[VectorChunkResult]:
    if not query.strip():
        return []
    if limit <= 0:
        raise ValueError("Search limit must be positive.")

    query_vector = validate_embedding(provider.embed_query(query), provider.dimensions)
    distance = DocumentChunk.embedding.op("<=>")(query_vector)
    similarity = literal(1.0) - distance
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
            similarity,
            DocumentChunk.page_start,
            DocumentChunk.page_end,
            DocumentChunk.heading,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.source_type == "library",
            matching_job,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance.asc())
        .limit(limit)
    ).all()
    return [
        VectorChunkResult(
            document_id=document_id,
            chunk_id=chunk_id,
            original_filename=filename,
            library_relative_path=relative_path,
            content=content,
            similarity=float(score),
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
            score,
            page_start,
            page_end,
            heading,
        ) in rows
    ]
