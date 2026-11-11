import math
from types import SimpleNamespace

import pytest

from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    FakeEmbeddingProvider,
    YandexEmbeddingProvider,
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


def test_yandex_provider_calls_embedding_api_and_validates_response(monkeypatch) -> None:
    captured = {}

    class Response:
        is_error = False
        status_code = 200

        @staticmethod
        def json():
            return {"embedding": [0.1, 0.2, 0.3]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.services.embeddings.httpx.post", fake_post)
    provider = YandexEmbeddingProvider(
        SimpleNamespace(
            yandex_cloud_api_key="api-key",
            yandex_cloud_folder="folder-id",
            yandex_embedding_model="text-search-doc",
            yandex_embedding_base_url="https://example.test",
            embedding_dimensions=3,
            llm_request_timeout_seconds=10,
        )
    )

    assert provider.embed_query("RNA localization") == [0.1, 0.2, 0.3]
    assert captured["url"] == (
        "https://example.test/foundationModels/v1/textEmbedding"
    )
    assert captured["headers"]["Authorization"] == "Api-Key api-key"
    assert captured["json"] == {
        "modelUri": "emb://folder-id/text-search-doc",
        "text": "RNA localization",
    }


def test_embedding_factory_selects_yandex_provider() -> None:
    provider = create_embedding_provider(
        SimpleNamespace(
            embedding_provider="yandex",
            yandex_cloud_api_key="api-key",
            yandex_cloud_folder="folder-id",
            yandex_embedding_model="text-search-doc",
            yandex_embedding_base_url="https://example.test",
            embedding_dimensions=3,
            llm_request_timeout_seconds=10,
        )
    )

    assert isinstance(provider, YandexEmbeddingProvider)


def test_yandex_provider_rejects_invalid_response_shape(monkeypatch) -> None:
    class Response:
        is_error = False
        status_code = 200

        @staticmethod
        def json():
            return {"embedding": [0.1]}

    monkeypatch.setattr("app.services.embeddings.httpx.post", lambda *args, **kwargs: Response())
    provider = YandexEmbeddingProvider(
        SimpleNamespace(
            yandex_cloud_api_key="api-key",
            yandex_cloud_folder="folder-id",
            embedding_dimensions=3,
        )
    )

    with pytest.raises(EmbeddingResponseError, match="expected 3"):
        provider.embed_query("text")
