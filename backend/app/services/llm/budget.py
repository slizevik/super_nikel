from dataclasses import dataclass
from math import ceil
from typing import Callable

from app.services.llm.base import TokenBudgetExceeded


@dataclass
class TokenReservation:
    reserved_tokens: int


class TokenBudget:
    MAX_IMAGE_RESPONSE_TOKENS = 1024
    MAX_EXTRACTION_RESPONSE_TOKENS = 32768
    MIN_RESPONSE_TOKENS = 128

    def __init__(
        self,
        limit: int,
        used: int = 0,
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("Token budget limit must be positive.")
        if used < 0:
            raise ValueError("Consumed token count cannot be negative.")
        self.limit = limit
        self.used = used
        self._on_change = on_change

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @staticmethod
    def estimate_text_tokens(text: str) -> int:
        if not text:
            return 0
        # A byte-per-token upper estimate avoids relying on a model tokenizer.
        return len(text.encode("utf-8"))

    @staticmethod
    def estimate_image_tokens(width: int, height: int) -> int:
        if width <= 0 or height <= 0:
            raise ValueError("Image dimensions must be positive.")
        tiles_x = ceil(width / 512)
        tiles_y = ceil(height / 512)
        return tiles_x * tiles_y * 512

    def reserve(
        self,
        estimated_input_tokens: int,
        preferred_response_tokens: int,
    ) -> tuple[TokenReservation, int]:
        if estimated_input_tokens < 0:
            raise ValueError("Estimated input token count cannot be negative.")
        if preferred_response_tokens <= 0:
            raise ValueError("Response token reservation must be positive.")

        available_for_response = self.remaining - estimated_input_tokens
        if available_for_response < self.MIN_RESPONSE_TOKENS:
            raise TokenBudgetExceeded(
                self.limit,
                self.used,
                estimated_input_tokens + self.MIN_RESPONSE_TOKENS,
            )

        response_tokens = min(preferred_response_tokens, available_for_response)
        reserved = estimated_input_tokens + response_tokens
        self.used += reserved
        self._persist()
        return TokenReservation(reserved), response_tokens

    def reconcile(
        self, reservation: TokenReservation, actual_total_tokens: int | None
    ) -> None:
        if actual_total_tokens is None:
            return
        if actual_total_tokens < 0:
            raise ValueError("Actual token usage cannot be negative.")

        self.used += actual_total_tokens - reservation.reserved_tokens
        reservation.reserved_tokens = actual_total_tokens
        self._persist()
        if self.used > self.limit:
            raise TokenBudgetExceeded(self.limit, self.used, 0)

    def _persist(self) -> None:
        if self._on_change is not None:
            self._on_change(self.used)
