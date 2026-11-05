import math
from types import SimpleNamespace

import pytest

from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    FakeEmbeddingProvider,
    create_embedding_provider,
    validate_embedding,
    validate_embeddings,
)


def test_fake_provider_is_deterministic_and_normalized() -> None:
    provider = FakeEmbeddingProvider(dimensions=8)

    first = provider.embed_query("RNA localization")
    second = provider.embed_query("RNA localization")

    assert first == second
    assert len(first) == 8
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_fake_provider_embeds_documents_in_batch() -> None:
    provider = FakeEmbeddingProvider(dimensions=4)

    vectors = provider.embed_documents(["first", "second"])

    assert len(vectors) == 2
    assert all(len(vector) == 4 for vector in vectors)


def test_embedding_validation_rejects_wrong_shape_and_non_finite_values() -> None:
    with pytest.raises(EmbeddingResponseError, match="expected 3"):
        validate_embedding([1.0, 2.0], 3)
    with pytest.raises(EmbeddingResponseError, match="non-finite"):
        validate_embedding([1.0, float("nan")], 2)
    with pytest.raises(EmbeddingResponseError, match="expected 2"):
        validate_embeddings([[1.0]], 2, 1)


def test_provider_factory_uses_configured_fake_provider() -> None:
    provider = create_embedding_provider(
        SimpleNamespace(
            embedding_provider="fake",
            embedding_model="test-model",
            embedding_dimensions=6,
        )
    )

    assert provider.model_name == "test-model"
    assert provider.dimensions == 6


def test_provider_factory_rejects_unknown_provider() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="Unsupported"):
        create_embedding_provider(
            SimpleNamespace(
                embedding_provider="remote",
                embedding_model="test-model",
                embedding_dimensions=6,
            )
        )
