import pytest

from app.services.llm.base import TokenBudgetExceeded
from app.services.llm.budget import TokenBudget


def test_budget_reserves_before_request_and_caps_output_to_remaining() -> None:
    persisted = []
    budget = TokenBudget(limit=10_000, on_change=persisted.append)

    reservation, output_tokens = budget.reserve(9000, 8192)

    assert output_tokens == 1000
    assert reservation.reserved_tokens == 10_000
    assert budget.used == 10_000
    assert persisted == [10_000]


def test_exhausted_budget_rejects_next_request_before_reserving() -> None:
    budget = TokenBudget(limit=100, used=80)

    with pytest.raises(TokenBudgetExceeded, match="token budget exceeded"):
        budget.reserve(20, 1024)

    assert budget.used == 80


def test_reported_usage_reconciles_reservation_and_persists_actual_usage() -> None:
    persisted = []
    budget = TokenBudget(limit=500, on_change=persisted.append)
    reservation, _output_tokens = budget.reserve(20, 40)

    budget.reconcile(reservation, actual_total_tokens=35)

    assert budget.used == 35
    assert persisted == [60, 35]


def test_actual_usage_over_budget_is_recorded_and_stops_pipeline() -> None:
    persisted = []
    budget = TokenBudget(limit=500, on_change=persisted.append)
    reservation, _output_tokens = budget.reserve(20, 40)

    with pytest.raises(TokenBudgetExceeded):
        budget.reconcile(reservation, actual_total_tokens=510)

    assert budget.used == 510
    assert persisted == [60, 510]


def test_failed_request_keeps_reservation_for_redelivery_budget() -> None:
    persisted = []
    budget = TokenBudget(limit=200, on_change=persisted.append)
    budget.reserve(20, 40)
    retried_budget = TokenBudget(limit=200, used=persisted[-1])

    with pytest.raises(TokenBudgetExceeded):
        retried_budget.reserve(41, 40)

    assert retried_budget.used == 60


def test_image_budget_uses_dimensions_without_counting_base64_payload() -> None:
    assert TokenBudget.estimate_image_tokens(1024, 768) == 2048


def test_text_estimate_is_conservative_for_multibyte_input() -> None:
    assert TokenBudget.estimate_text_tokens("Ni") == 2
    assert TokenBudget.estimate_text_tokens("никель") == len(
        "никель".encode("utf-8")
    )


def test_budget_rejects_requests_with_too_little_response_headroom() -> None:
    budget = TokenBudget(limit=10_000, used=9000)

    with pytest.raises(TokenBudgetExceeded):
        budget.reserve(900, 1024)

    assert budget.used == 9000
