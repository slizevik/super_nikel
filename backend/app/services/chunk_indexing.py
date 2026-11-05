"""Persistence helpers for replacing a document's indexed chunks atomically."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete

from app.db.models import DocumentChunk
from app.services.chunking import DocumentChunkDraft, build_chunks
from app.services.embeddings import EmbeddingProvider, validate_embeddings
from app.services.pdf_parser import ParsedTextBlock


def build_indexed_chunks(
    blocks: Sequence[ParsedTextBlock],
    provider: EmbeddingProvider,
    *,
    batch_size: int = 32,
    target_tokens: int = 600,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[tuple[DocumentChunkDraft, list[float]]]:
    if batch_size <= 0:
        raise ValueError("Embedding batch size must be positive.")
    drafts = build_chunks(
        blocks,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    indexed: list[tuple[DocumentChunkDraft, list[float]]] = []
    for start in range(0, len(drafts), batch_size):
        batch = drafts[start : start + batch_size]
        vectors = validate_embeddings(
            provider.embed_documents([draft.content for draft in batch]),
            len(batch),
            provider.dimensions,
        )
        indexed.extend(zip(batch, vectors, strict=True))
    return indexed


def replace_document_chunks(
    session,
    document_id: UUID,
    blocks: Sequence[ParsedTextBlock],
    provider: EmbeddingProvider,
    *,
    batch_size: int = 32,
    target_tokens: int = 600,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> int:
    """Prepare vectors first, then replace the document's chunks in one transaction."""
    indexed = build_indexed_chunks(
        blocks,
        provider,
        batch_size=batch_size,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    session.add_all(
        DocumentChunk(
            document_id=document_id,
            chunk_index=draft.chunk_index,
            content=draft.content,
            token_count=draft.token_count,
            page_start=draft.page_start,
            page_end=draft.page_end,
            heading=draft.heading,
            embedding=vector,
            embedding_model=provider.model_name,
            chunk_metadata={
                "page_start": draft.page_start,
                "page_end": draft.page_end,
                "heading": draft.heading,
                "char_start": draft.char_start,
                "char_end": draft.char_end,
                "chunker_version": "v1",
            },
        )
        for draft, vector in indexed
    )
    return len(indexed)
