"""Hybrid lexical and semantic retrieval over indexed document chunks."""

from dataclasses import dataclass
from uuid import UUID

from app.services.embeddings import EmbeddingProvider
from app.services.full_text_search import FullTextChunkResult, search_chunks_full_text
from app.services.vector_search import VectorChunkResult, search_chunks_vector


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    chunk_id: UUID
    original_filename: str
    library_relative_path: str | None
    content: str
    excerpt: str
    page_start: int | None
    page_end: int | None
    heading: str | None
    lexical_score: float
    semantic_score: float
    hybrid_score: float


def _normalize_lexical(results: list[FullTextChunkResult]) -> dict[UUID, float]:
    maximum = max((result.score for result in results), default=0.0)
    if maximum <= 0:
        return {result.chunk_id: 0.0 for result in results}
    return {result.chunk_id: result.score / maximum for result in results}


def _normalize_semantic(results: list[VectorChunkResult]) -> dict[UUID, float]:
    return {
        result.chunk_id: max(0.0, min(1.0, (result.similarity + 1.0) / 2.0))
        for result in results
    }


def merge_retrieval_results(
    lexical_results: list[FullTextChunkResult],
    semantic_results: list[VectorChunkResult],
    *,
    lexical_weight: float = 0.45,
    semantic_weight: float = 0.55,
    limit: int = 8,
) -> list[RetrievedChunk]:
    if lexical_weight < 0 or semantic_weight < 0:
        raise ValueError("Retrieval weights cannot be negative.")
    if lexical_weight + semantic_weight <= 0:
        raise ValueError("At least one retrieval weight must be positive.")
    if limit <= 0:
        raise ValueError("Search limit must be positive.")

    lexical_scores = _normalize_lexical(lexical_results)
    semantic_scores = _normalize_semantic(semantic_results)
    sources = {result.chunk_id: result for result in lexical_results}
    sources.update(
        {
            result.chunk_id: result
            for result in semantic_results
            if result.chunk_id not in sources
        }
    )
    total_weight = lexical_weight + semantic_weight
    merged: list[RetrievedChunk] = []
    for chunk_id in sources:
        lexical = lexical_scores.get(chunk_id, 0.0)
        semantic = semantic_scores.get(chunk_id, 0.0)
        source = sources[chunk_id]
        excerpt = source.excerpt if isinstance(source, FullTextChunkResult) else source.content
        merged.append(
            RetrievedChunk(
                document_id=source.document_id,
                chunk_id=source.chunk_id,
                original_filename=source.original_filename,
                library_relative_path=source.library_relative_path,
                content=source.content,
                excerpt=excerpt,
                page_start=source.page_start,
                page_end=source.page_end,
                heading=source.heading,
                lexical_score=lexical,
                semantic_score=semantic,
                hybrid_score=(lexical_weight * lexical + semantic_weight * semantic)
                / total_weight,
            )
        )
    merged.sort(key=lambda result: result.hybrid_score, reverse=True)

    deduplicated: list[RetrievedChunk] = []
    seen_content: set[str] = set()
    for result in merged:
        fingerprint = " ".join(result.content.lower().split())
        if fingerprint in seen_content:
            continue
        seen_content.add(fingerprint)
        deduplicated.append(result)
        if len(deduplicated) == limit:
            break
    return deduplicated


def search_library(
    session,
    query: str,
    embedding_provider: EmbeddingProvider,
    *,
    translated_query: str | None = None,
    limit: int = 8,
    lexical_weight: float = 0.45,
    semantic_weight: float = 0.55,
) -> list[RetrievedChunk]:
    if not query.strip():
        return []
    if limit <= 0:
        raise ValueError("Search limit must be positive.")
    candidate_limit = max(limit * 2, 8)
    lexical_results = search_chunks_full_text(
        session,
        query,
        translated_query=translated_query,
        limit=candidate_limit,
    )
    semantic_results = search_chunks_vector(
        session,
        query,
        embedding_provider,
        limit=candidate_limit,
    )
    return merge_retrieval_results(
        lexical_results,
        semantic_results,
        lexical_weight=lexical_weight,
        semantic_weight=semantic_weight,
        limit=limit,
    )
