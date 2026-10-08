from dataclasses import dataclass
from typing import Callable, Protocol

from app.schemas.extraction import ExtractionResult, ImageDescription


@dataclass(frozen=True)
class ImageInput:
    image_id: str
    content: bytes
    media_type: str
    caption: str | None
    width: int
    height: int


class LLMProviderError(RuntimeError):
    pass


class LLMConfigurationError(LLMProviderError):
    pass


class LLMResponseError(LLMProviderError):
    pass


class TokenBudgetExceeded(LLMProviderError):
    def __init__(self, limit: int, used: int, required: int) -> None:
        self.limit = limit
        self.used = used
        self.required = required
        super().__init__(
            f"PDF token budget exceeded: limit={limit}, used={used}, "
            f"next_request_reservation={required}."
        )


class LLMProvider(Protocol):
    def describe_image(
        self, image: ImageInput, document_context: str
    ) -> ImageDescription: ...

    def extract_entities(
        self,
        document_text: str,
        image_descriptions: list[ImageDescription],
        on_raw_response: Callable[[str], None] | None = None,
    ) -> ExtractionResult: ...
