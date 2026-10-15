import json
import re
import time
from collections.abc import Callable
from uuid import uuid4

import httpx
import structlog
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.extraction import ExtractionCandidates, ImageDescription
from app.services.llm.base import (
    ImageInput,
    LLMConfigurationError,
    LLMResponseError,
    TokenBudgetExceeded,
)
from app.services.llm.budget import TokenBudget, TokenReservation
from app.services.llm.prompts import (
    ENTITY_EXTRACTION_INSTRUCTIONS,
    IMAGE_DESCRIPTION_INSTRUCTIONS,
)

logger = structlog.get_logger(__name__)


class GigaChatProvider:
    _IMAGE_EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/tiff": ".tiff",
        "image/bmp": ".bmp",
    }

    def __init__(self, settings: Settings, token_budget: TokenBudget) -> None:
        if not settings.gigachat_credentials:
            raise LLMConfigurationError("GIGACHAT_CREDENTIALS is required.")
        self._credentials = settings.gigachat_credentials
        self._scope = settings.gigachat_scope
        self._text_model = settings.gigachat_model
        self._vision_model = (
            settings.gigachat_vision_model or settings.gigachat_model
        )
        self._api_base_url = settings.gigachat_api_base_url.rstrip("/")
        self._oauth_url = settings.gigachat_oauth_url
        self._timeout = httpx.Timeout(settings.llm_request_timeout_seconds)
        self._max_output_tokens = settings.gigachat_max_output_tokens
        self._token_budget = token_budget
        self._access_token: str | None = None
        self._token_expires_at = 0.0

    def describe_image(
        self, image: ImageInput, document_context: str
    ) -> ImageDescription:
        extension = self._IMAGE_EXTENSIONS.get(image.media_type)
        if extension is None:
            raise LLMResponseError(
                f"GigaChat does not support image media type '{image.media_type}'."
            )
        caption = image.caption or "No caption is available."
        context = document_context[:12_000]
        prompt = (
            f"{IMAGE_DESCRIPTION_INSTRUCTIONS}\n"
            f"image_id: {image.image_id}\n"
            f"caption: {caption}\n"
            f"document context:\n{context}"
        )
        estimated_tokens = (
            TokenBudget.estimate_text_tokens(prompt)
            + TokenBudget.estimate_image_tokens(image.width, image.height)
        )
        file_id = self._upload_image(image, extension)
        try:
            response, _reservation = self._chat_completion(
                model=self._vision_model,
                operation="image_description",
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "attachments": [file_id],
                    }
                ],
                estimated_input_tokens=estimated_tokens,
                preferred_response_tokens=TokenBudget.MAX_IMAGE_RESPONSE_TOKENS,
            )
            payload = self._parse_json_response(response)
            payload.setdefault("image_id", image.image_id)
            payload.setdefault("caption", image.caption)
            try:
                result = ImageDescription.model_validate(payload)
            except ValidationError as error:
                raise LLMResponseError(
                    "GigaChat vision response did not match "
                    "the image-description schema."
                ) from error
        except (LLMResponseError, TokenBudgetExceeded):
            self._delete_after_failure(file_id)
            raise
        self._delete_file(file_id)
        return result

    def extract_entities(
        self,
        document_text: str,
        image_descriptions: list[ImageDescription],
        on_raw_response: Callable[[str], None] | None = None,
    ) -> ExtractionCandidates:
        if not document_text.strip():
            raise LLMResponseError(
                "Entity extraction requires non-empty document text."
            )

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
            operation="entity_extraction",
            messages=[
                {"role": "system", "content": ENTITY_EXTRACTION_INSTRUCTIONS},
                {"role": "user", "content": user_content},
            ],
            estimated_input_tokens=TokenBudget.estimate_text_tokens(
                ENTITY_EXTRACTION_INSTRUCTIONS + user_content
            ),
            preferred_response_tokens=min(
                TokenBudget.MAX_EXTRACTION_RESPONSE_TOKENS,
                self._max_output_tokens,
            ),
        )
        if on_raw_response is not None:
            on_raw_response(response)
        payload = self._parse_json_response(response)
        try:
            return ExtractionCandidates.model_validate(payload)
        except ValidationError as error:
            details = "; ".join(
                f"{issue.get('loc', ['<unknown>'])}: "
                f"{issue.get('msg', 'invalid value')}"
                for issue in error.errors(include_url=False)
            )
            raise LLMResponseError(
                "GigaChat response did not match the entity-extraction schema: "
                f"{details or str(error)}"
            ) from error

    def _upload_image(self, image: ImageInput, extension: str) -> str:
        try:
            response = httpx.post(
                f"{self._api_base_url}/files",
                headers=self._authorization_headers(),
                data={"purpose": "general"},
                files={
                    "file": (
                        f"{image.image_id}{extension}",
                        image.content,
                        image.media_type,
                    )
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise LLMResponseError("GigaChat image upload timed out.") from error
        except httpx.RequestError as error:
            raise LLMResponseError(
                "Could not connect to the GigaChat file endpoint: "
                f"{error.__class__.__name__}."
            ) from error
        if response.is_error:
            raise LLMResponseError(
                f"GigaChat image upload returned HTTP {response.status_code}."
            )
        try:
            response_body = response.json()
            file_id = response_body["id"]
            if not isinstance(file_id, str) or not file_id:
                raise ValueError("Missing file id.")
            return file_id
        except (ValueError, KeyError, TypeError) as error:
            raise LLMResponseError(
                "GigaChat returned an unexpected image-upload response."
            ) from error

    def _delete_file(self, file_id: str) -> None:
        try:
            response = httpx.post(
                f"{self._api_base_url}/files/{file_id}/delete",
                headers=self._authorization_headers(),
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise LLMResponseError("GigaChat image cleanup timed out.") from error
        except httpx.RequestError as error:
            raise LLMResponseError(
                "Could not connect to the GigaChat file endpoint during cleanup: "
                f"{error.__class__.__name__}."
            ) from error
        if response.is_error:
            raise LLMResponseError(
                f"GigaChat image cleanup returned HTTP {response.status_code}."
            )

    def _delete_after_failure(self, file_id: str) -> None:
        try:
            self._delete_file(file_id)
        except LLMResponseError as error:
            logger.warning(
                "gigachat_image_cleanup_failed",
                error_type=error.__class__.__name__,
            )

    def _chat_completion(
        self,
        model: str,
        operation: str,
        messages: list[dict[str, object]],
        estimated_input_tokens: int,
        preferred_response_tokens: int,
    ) -> tuple[str, TokenReservation]:
        reservation, max_output_tokens = self._token_budget.reserve(
            estimated_input_tokens,
            min(preferred_response_tokens, self._max_output_tokens),
        )
        try:
            response = httpx.post(
                f"{self._api_base_url}/chat/completions",
                headers=self._authorization_headers(),
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "max_tokens": max_output_tokens,
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise LLMResponseError("GigaChat request timed out.") from error
        except httpx.RequestError as error:
            raise LLMResponseError(
                "Could not connect to the configured GigaChat endpoint: "
                f"{error.__class__.__name__}."
            ) from error
        if response.is_error:
            raise LLMResponseError(
                f"GigaChat returned HTTP {response.status_code}."
            )
        try:
            response_body = response.json()
            usage = response_body.get("usage")
            actual_tokens = self._actual_total_tokens(usage)
            self._token_budget.reconcile(reservation, actual_tokens)
            choice = response_body["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise LLMResponseError(
                    "GigaChat response content must be a string."
                )
        except LLMResponseError:
            raise
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
            raise LLMResponseError(
                "GigaChat returned an unexpected chat-completion response."
            ) from error

        logger.info(
            "gigachat_chat_completion_received",
            operation=operation,
            finish_reason=(
                choice.get("finish_reason")[:64]
                if isinstance(choice.get("finish_reason"), str)
                else None
            ),
            content_length=len(content),
            usage=self._safe_usage(usage),
        )
        return content, reservation

    def _authorization_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_access_token()}"}

    def _get_access_token(self) -> str:
        if (
            self._access_token is not None
            and time.time() < self._token_expires_at - 60
        ):
            return self._access_token
        try:
            response = httpx.post(
                self._oauth_url,
                headers={
                    "Authorization": f"Basic {self._credentials}",
                    "RqUID": str(uuid4()),
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={"scope": self._scope},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise LLMResponseError(
                "GigaChat access-token request timed out."
            ) from error
        except httpx.RequestError as error:
            raise LLMResponseError(
                "Could not connect to the GigaChat access-token endpoint: "
                f"{error.__class__.__name__}."
            ) from error
        if response.is_error:
            raise LLMResponseError(
                f"GigaChat access-token request returned HTTP {response.status_code}."
            )
        try:
            response_body = response.json()
            access_token = response_body["access_token"]
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Missing access token.")
            expires_at = response_body.get("expires_at")
            if isinstance(expires_at, (int, float)):
                self._token_expires_at = float(expires_at) / 1000
            else:
                self._token_expires_at = time.time() + 29 * 60
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise LLMResponseError(
                "GigaChat returned an unexpected access-token response."
            ) from error
        self._access_token = access_token
        return access_token

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
            raise LLMResponseError("GigaChat returned invalid JSON.") from error
        if not isinstance(result, dict):
            raise LLMResponseError("GigaChat JSON response must be an object.")
        return result

    @staticmethod
    def _actual_total_tokens(usage: object) -> int | None:
        if not isinstance(usage, dict):
            return None
        total = usage.get("total_tokens")
        if isinstance(total, int) and total >= 0:
            return total
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            return prompt + completion
        return None

    @staticmethod
    def _safe_usage(usage: object) -> dict[str, int] | None:
        if not isinstance(usage, dict):
            return None
        return {
            key: value
            for key, value in usage.items()
            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and isinstance(value, int)
        }
