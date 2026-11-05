from uuid import uuid4

import pytest

from app.services.full_text_search import FullTextChunkResult
from app.services.retrieval import merge_retrieval_results
from app.services.vector_search import VectorChunkResult


def lexical(chunk_id, score, content="A paper fragment"):
    return FullTextChunkResult(
        document_id=uuid4(),
        chunk_id=chunk_id,
        original_filename="paper.pdf",
        library_relative_path="paper.pdf",
        content=content,
        excerpt=content,
        score=score,
        page_start=2,
        page_end=2,
        heading="Methods",
    )


def semantic(chunk_id, similarity, content="A paper fragment"):
    return VectorChunkResult(
        document_id=uuid4(),
        chunk_id=chunk_id,
        original_filename="paper.pdf",
        library_relative_path="paper.pdf",
        content=content,
        similarity=similarity,
        page_start=2,
        page_end=2,
        heading="Methods",
    )


def test_merge_normalizes_scores_and_combines_same_chunk() -> None:
    chunk_id = uuid4()

    results = merge_retrieval_results(
        [lexical(chunk_id, 2.0)],
        [semantic(chunk_id, 1.0)],
        limit=5,
    )

    assert len(results) == 1
    assert results[0].lexical_score == 1.0
    assert results[0].semantic_score == 1.0
    assert results[0].hybrid_score == 1.0


def test_merge_deduplicates_identical_content() -> None:
    first = uuid4()
    second = uuid4()

    results = merge_retrieval_results(
        [lexical(first, 2.0), lexical(second, 1.0)],
        [],
        limit=5,
    )

    assert len(results) == 1


def test_merge_rejects_invalid_weights_and_limit() -> None:
    with pytest.raises(ValueError, match="weights"):
        merge_retrieval_results([], [], lexical_weight=-1)
    with pytest.raises(ValueError, match="positive"):
        merge_retrieval_results([], [], lexical_weight=0, semantic_weight=0)
    with pytest.raises(ValueError, match="positive"):
        merge_retrieval_results([], [], limit=0)
