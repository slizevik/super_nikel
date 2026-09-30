import json
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.extraction import ExtractionResult, ImageDescription
from app.services.llm.base import LLMConfigurationError, LLMResponseError
from app.services.llm.budget import TokenBudget
from app.services.llm.factory import create_llm_provider
from app.services.llm.yandex import YandexGPTProvider


def test_provider_factory_fails_clearly_without_yandex_credentials() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder="folder-id",
        yandex_cloud_api_key=None,
    )

    with pytest.raises(LLMConfigurationError, match="YANDEX_CLOUD_API_KEY"):
        create_llm_provider(settings, TokenBudget(1000))


def test_provider_factory_requires_yandex_folder_id() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder=None,
        yandex_cloud_api_key="test-key",
    )

    with pytest.raises(LLMConfigurationError, match="YANDEX_CLOUD_FOLDER"):
        create_llm_provider(settings, TokenBudget(1000))


def test_yandex_provider_sends_json_extraction_request(monkeypatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder="folder-id",
        yandex_cloud_api_key="test-key",
        yandex_cloud_model="yandexgpt/latest",
        yandex_cloud_base_url="https://llm.example.test/v1",
    )
    persisted_usage = []
    budget = TokenBudget(100_000, on_change=persisted_usage.append)
    provider = YandexGPTProvider(settings, budget)
    payload = {
        "entities": [
            {
                "id": "e1",
                "type": "Material",
                "label": "nickel",
                "canonical_label": "Ni",
                "aliases": ["nickel"],
                "evidence": "The sample contains nickel.",
            }
        ],
        "relationships": [],
        "unclassified_entities": [],
    }
    captured = {}

    def fake_post(url, **kwargs):
        assert persisted_usage and persisted_usage[0] > 0
        captured["url"] = url
        captured.update(kwargs)
        return SimpleNamespace(
            is_error=False,
            json=lambda: {
                "choices": [{"message": {"content": json.dumps(payload)}}],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 20,
                    "total_tokens": 70,
                },
            },
        )

    monkeypatch.setattr("app.services.llm.yandex.httpx.post", fake_post)

    result = provider.extract_entities("The sample contains nickel.", [])

    assert isinstance(result, ExtractionResult)
    assert result.entities[0].canonical_label == "Ni"
    assert captured["url"] == "https://llm.example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Api-Key test-key"
    assert captured["json"]["model"] == "gpt://folder-id/yandexgpt/latest"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["max_tokens"] <= TokenBudget.MAX_EXTRACTION_RESPONSE_TOKENS
    assert persisted_usage[-1] == 70


def test_yandex_provider_serializes_image_as_data_url(monkeypatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder="folder-id",
        yandex_cloud_api_key="test-key",
    )
    provider = YandexGPTProvider(settings, TokenBudget(100_000))
    captured = {}

    def fake_post(_url, **kwargs):
        captured.update(kwargs)
        payload = {
            "image_id": "image-0001",
            "kind": "chart",
            "useful": True,
            "description": "A chart.",
            "key_information": "Nickel recovery rises.",
            "caption": "Recovery",
        }
        return SimpleNamespace(
            is_error=False,
            json=lambda: {
                "choices": [{"message": {"content": json.dumps(payload)}}]
            },
        )

    monkeypatch.setattr("app.services.llm.yandex.httpx.post", fake_post)
    result = provider.describe_image(
        SimpleNamespace(
            image_id="image-0001",
            content=b"png bytes",
            media_type="image/png",
            caption="Recovery",
            width=16,
            height=16,
        ),
        "Nickel leaching experiment.",
    )

    assert isinstance(result, ImageDescription)
    assert captured["json"]["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_yandex_provider_rejects_invalid_json_response(monkeypatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder="folder-id",
        yandex_cloud_api_key="test-key",
    )
    provider = YandexGPTProvider(settings, TokenBudget(100_000))
    monkeypatch.setattr(
        "app.services.llm.yandex.httpx.post",
        lambda *_args, **_kwargs: SimpleNamespace(
            is_error=False,
            json=lambda: {"choices": [{"message": {"content": "not-json"}}]},
        ),
    )

    with pytest.raises(LLMResponseError, match="invalid JSON"):
        provider.extract_entities("Nickel.", [])


def test_yandex_provider_reports_tls_trust_failure_clearly(monkeypatch) -> None:
    settings = Settings(
        database_url="postgresql+psycopg://localhost/nikelpower",
        yandex_cloud_folder="folder-id",
        yandex_cloud_api_key="test-key",
    )
    provider = YandexGPTProvider(settings, TokenBudget(100_000))
    monkeypatch.setattr(
        "app.services.llm.yandex.httpx.post",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in chain"
            )
        ),
    )

    with pytest.raises(LLMResponseError, match="TLS certificate verification failed"):
        provider.extract_entities("Nickel.", [])


def test_extraction_contract_rejects_unknown_entity_type() -> None:
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(
            {
                "entities": [
                    {
                        "id": "e1",
                        "type": "Unknown",
                        "label": "item",
                        "canonical_label": "item",
                        "evidence": "item",
                    }
                ],
                "relationships": [],
                "unclassified_entities": [],
            }
        )
