import base64
import json
import re

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.extraction import ExtractionResult, ImageDescription
from app.services.llm.base import (
    ImageInput,
    LLMConfigurationError,
    LLMResponseError,
)
from app.services.llm.budget import TokenBudget, TokenReservation


ENTITY_EXTRACTION_INSTRUCTIONS = """\
Extract only entities and relationships explicitly supported by the supplied
document. Return one JSON object with exactly these keys:
{
  "entities": [
    {
      "id": "e1",
      "type": "Material|Process|Equipment|Property|Experiment|Publication|Document|Expert|Facility|Condition|Country|Claim",
      "label": "source-language label",
      "canonical_label": "canonical name",
      "aliases": [],
      "evidence": "verbatim supporting excerpt"
    }
  ],
  "relationships": [
    {
      "source_id": "e1",
      "target_id": "e2",
      "type": "uses_material|operates_at_condition|produces_output|described_in|validated_by|contradicts",
      "evidence": "verbatim supporting excerpt"
    }
  ],
  "unclassified_entities": [
    {"text": "entity text", "context": "verbatim surrounding context"}
  ]
}
Use at most 5 entities of each type and 10 relationships. Entity IDs must be
unique and every relationship endpoint must reference an entity in this JSON.
Use only the listed types and relationship direction:
Process|Experiment -> Material (uses_material);
Process|Equipment -> Condition (operates_at_condition);
Process|Experiment -> Property (produces_output);
any listed type except Document -> Document (described_in);
Experiment|Claim -> Expert|Publication (validated_by);
Claim -> Claim (contradicts).
Do not extract generic noise such as "research", "method", or "result".
Put plausible entities that do not fit the closed type list in
unclassified_entities; never invent an ontology type. Do not infer facts,
authors, countries, dates, or relationships that are not in the source.
Return JSON only.
"""

IMAGE_DESCRIPTION_INSTRUCTIONS = """\
Classify this document image as chart, table, diagram, photo, or other.
For charts, tables, and diagrams, describe the key materials-science facts
that are visibly supported by the image. For other images, state whether the
image is useful for understanding the document; if not, set useful=false and
say so. Do not infer unreadable values. Return JSON only with keys:
image_id, kind, useful, description, key_information, caption.
"""


class YandexGPTProvider:
    def __init__(self, settings: Settings, token_budget: TokenBudget) -> None:
        if not settings.yandex_cloud_api_key or not settings.yandex_cloud_folder:
            raise LLMConfigurationError(
                "YANDEX_CLOUD_API_KEY and YANDEX_CLOUD_FOLDER are required."
            )
        self._api_key = settings.yandex_cloud_api_key
        self._folder_id = settings.yandex_cloud_folder
        self._text_model = settings.yandex_cloud_model
        self._vision_model = settings.yandex_vision_model or settings.yandex_cloud_model
        self._base_url = settings.yandex_cloud_base_url.rstrip("/")
        self._timeout = httpx.Timeout(settings.llm_request_timeout_seconds)
        self._token_budget = token_budget

    def describe_image(
        self, image: ImageInput, document_context: str
    ) -> ImageDescription:
        image_data = base64.b64encode(image.content).decode("ascii")
        caption = image.caption or "No caption is available."
        context = document_context[:12_000]
        content = [
            {
                "type": "text",
                "text": (
                    f"{IMAGE_DESCRIPTION_INSTRUCTIONS}\n"
                    f"image_id: {image.image_id}\n"
                    f"caption: {caption}\n"
                    f"document context:\n{context}"
                ),
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image.media_type};base64,{image_data}"
                },
            },
        ]
        response, _reservation = self._chat_completion(
            model=self._vision_model,
            messages=[{"role": "user", "content": content}],
            estimated_input_tokens=(
                TokenBudget.estimate_text_tokens(content[0]["text"])
                + TokenBudget.estimate_image_tokens(image.width, image.height)
            ),
            preferred_response_tokens=TokenBudget.MAX_IMAGE_RESPONSE_TOKENS,
        )
        payload = self._parse_json_response(response)
        payload.setdefault("image_id", image.image_id)
        payload.setdefault("caption", image.caption)
        try:
            return ImageDescription.model_validate(payload)
        except ValidationError as error:
            raise LLMResponseError(
                "Yandex vision response did not match the image-description schema."
            ) from error

    def extract_entities(
        self, document_text: str, image_descriptions: list[ImageDescription]
    ) -> ExtractionResult:
        descriptions = [
            description.model_dump(mode="json") for description in image_descriptions
        ]
        user_content = (
            "Extract entities and relationships from this document.\n"
            "Descriptions of document images (use only when consistent with the "
            "document text):\n"
            f"{json.dumps(descriptions, ensure_ascii=False)}\n\n"
            "Document text:\n"
            f"{document_text}"
        )
        response, _reservation = self._chat_completion(
            model=self._text_model,
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_INSTRUCTIONS},
                {"role": "user", "content": user_content},
            ],
            estimated_input_tokens=TokenBudget.estimate_text_tokens(
                ENTITY_EXTRACTION_INSTRUCTIONS + user_content
            ),
            preferred_response_tokens=TokenBudget.MAX_EXTRACTION_RESPONSE_TOKENS,
        )
        payload = self._normalize_extraction_payload(self._parse_json_response(response))
        try:
            return ExtractionResult.model_validate(payload)
        except ValidationError as error:
            validation_details = "; ".join(
                f"{issue.get('loc', ['<unknown>'])}: {issue.get('msg', 'invalid value')}"
                for issue in error.errors(include_url=False)
            )
            raise LLMResponseError(
                "Yandex GPT response did not match the entity-extraction schema: "
                f"{validation_details or str(error)}"
            ) from error

    def _chat_completion(
        self,
        model: str,
        messages: list[dict],
        estimated_input_tokens: int,
        preferred_response_tokens: int,
    ) -> tuple[str, TokenReservation]:
        reservation, max_output_tokens = self._token_budget.reserve(
            estimated_input_tokens, preferred_response_tokens
        )
        model_uri = self._model_uri(model)
        url = f"{self._base_url}/chat/completions"
        try:
            response = httpx.post(
                url,
                headers={
                    "Authorization": f"Api-Key {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_uri,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "max_tokens": max_output_tokens,
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise LLMResponseError("Yandex GPT request timed out.") from error
        except httpx.RequestError as error:
            if "CERTIFICATE_VERIFY_FAILED" in str(error):
                raise LLMResponseError(
                    "Yandex GPT TLS certificate verification failed in the "
                    "backend/worker container. Configure the trusted CA "
                    "certificate; TLS verification must remain enabled."
                ) from error
            raise LLMResponseError(
                f"Could not connect to the configured Yandex GPT endpoint: {error.__class__.__name__}."
            ) from error

        if response.is_error:
            raise LLMResponseError(
                f"Yandex GPT returned HTTP {response.status_code}."
            )
        try:
            response_body = response.json()
            if not isinstance(response_body, dict):
                raise LLMResponseError(
                    "Yandex GPT returned an unexpected chat-completion response."
                )
            usage = response_body.get("usage")
            actual_tokens = self._actual_total_tokens(usage)
            self._token_budget.reconcile(reservation, actual_tokens)
            content = response_body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise LLMResponseError(
                    "Yandex GPT response content must be a string."
                )
            return content, reservation
        except LLMResponseError:
            raise
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMResponseError(
                "Yandex GPT returned an unexpected chat-completion response."
            ) from error

    def _model_uri(self, model: str) -> str:
        if model.startswith("gpt://"):
            return model
        return f"gpt://{self._folder_id}/{model.lstrip('/')}"

    @staticmethod
    def _actual_total_tokens(usage: object) -> int | None:
        if not isinstance(usage, dict):
            return None
        total = usage.get("total_tokens")
        if isinstance(total, int) and total >= 0:
            return total
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        if isinstance(prompt, int) and isinstance(completion, int):
            return prompt + completion
        return None

    @staticmethod
    def _parse_json_response(content: str) -> dict:
        normalized = content.strip()
        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```", normalized, flags=re.DOTALL | re.IGNORECASE
        )
        if fenced:
            normalized = fenced.group(1)
        try:
            result = json.loads(normalized)
        except json.JSONDecodeError as error:
            raise LLMResponseError("Yandex GPT returned invalid JSON.") from error
        if not isinstance(result, dict):
            raise LLMResponseError("Yandex GPT JSON response must be an object.")
        return result

    @staticmethod
    def _normalize_extraction_payload(payload: dict) -> dict:
        if "entities" in payload and "relationships" in payload:
            return payload

        candidate = payload.get("result")
        if isinstance(candidate, dict):
            if "entities" in candidate and "relationships" in candidate:
                return candidate
            nested = candidate.get("data")
            if isinstance(nested, dict) and "entities" in nested and "relationships" in nested:
                return nested

        if "data" in payload and isinstance(payload["data"], dict):
            nested = payload["data"]
            if "entities" in nested and "relationships" in nested:
                return nested

        if "output" in payload and isinstance(payload["output"], dict):
            nested = payload["output"]
            if "entities" in nested and "relationships" in nested:
                return nested

        raise LLMResponseError(
            "Yandex GPT response did not contain the required extraction payload: "
            "expected an object with 'entities' and 'relationships'."
        )
