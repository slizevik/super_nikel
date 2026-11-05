from types import SimpleNamespace

import pytest

from app.services.embeddings import FakeEmbeddingProvider
from app.services.vector_search import search_chunks_vector


class EmptySession:
    def execute(self, _statement):
        return SimpleNamespace(all=lambda: [])


def test_vector_search_returns_empty_for_blank_query_without_embedding_call() -> None:
    class Provider:
        dimensions = 4

        def embed_query(self, _query):
            raise AssertionError("Blank query must not be embedded")

    assert search_chunks_vector(EmptySession(), "  ", Provider()) == []


def test_vector_search_validates_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        search_chunks_vector(
            EmptySession(),
            "RNA localization",
            FakeEmbeddingProvider(dimensions=4),
            limit=0,
        )


def test_vector_search_builds_query_with_fake_embedding_provider() -> None:
    results = search_chunks_vector(
        EmptySession(),
        "RNA localization",
        FakeEmbeddingProvider(dimensions=4),
        limit=3,
    )

    assert results == []
