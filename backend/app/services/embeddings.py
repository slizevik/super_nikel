"""Provider-neutral embedding contracts and a deterministic test provider."""

from collections.abc import Sequence
import hashlib
import math
from typing import Protocol


class EmbeddingProviderError(RuntimeError):
    """Base error for embedding configuration and provider failures."""


class EmbeddingConfigurationError(EmbeddingProviderError):
    """Raised when the selected embedding provider is not configured."""


class EmbeddingResponseError(EmbeddingProviderError):
    """Raised when a provider returns vectors with an invalid shape."""


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def validate_embedding(vector: Sequence[float], dimensions: int) -> list[float]:
    if len(vector) != dimensions:
        raise EmbeddingResponseError(
            f"Embedding has {len(vector)} dimensions; expected {dimensions}."
        )
    result = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in result):
        raise EmbeddingResponseError("Embedding contains a non-finite value.")
    return result


def validate_embeddings(
    vectors: Sequence[Sequence[float]],
    expected_count: int,
    dimensions: int,
) -> list[list[float]]:
    if len(vectors) != expected_count:
        raise EmbeddingResponseError(
            f"Embedding provider returned {len(vectors)} vectors; "
            f"expected {expected_count}."
        )
    return [validate_embedding(vector, dimensions) for vector in vectors]


class FakeEmbeddingProvider:
    """Deterministic local provider for tests and development."""

    def __init__(self, model_name: str = "fake", dimensions: int = 1024) -> None:
        if not model_name.strip() or dimensions <= 0:
            raise ValueError("Embedding model name and dimensions are required.")
        self._model_name = model_name
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed(self, text: str) -> list[float]:
        if not text.strip():
            raise EmbeddingResponseError("Cannot embed empty text.")
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self._dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        norm = math.sqrt(sum(value * value for value in values[: self._dimensions]))
        return [value / norm for value in values[: self._dimensions]]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return validate_embeddings(
            [self._embed(text) for text in texts],
            len(texts),
            self._dimensions,
        )

    def embed_query(self, text: str) -> list[float]:
        return validate_embedding(self._embed(text), self._dimensions)


def create_embedding_provider(settings) -> EmbeddingProvider:
    provider_name = getattr(settings, "embedding_provider", "fake").strip().lower()
    if provider_name == "fake":
        return FakeEmbeddingProvider(
            model_name=getattr(settings, "embedding_model", "emb/latest"),
            dimensions=getattr(settings, "embedding_dimensions", 1024),
        )
    raise EmbeddingConfigurationError(
        f"Unsupported EMBEDDING_PROVIDER '{provider_name}'. "
        "Configure EMBEDDING_PROVIDER=fake until a production provider is added."
    )
