import pytest

from boq.boq_generator import BoQItem
from boq.cost_estimator import calculate_costs, calculate_item_cost
from utils.exceptions import BoqValidationError, MissingRateError


def make_item(
    item_id: str = "wall-1",
    quantity: float = 10,
    rate: float = 100,
    rate_source: str = "user-entered",
) -> BoQItem:
    return BoQItem(
        item_id=item_id,
        name="Wall",
        description="Test wall",
        quantity=quantity,
        unit="m",
        rate=rate,
        total=quantity * rate,
        status="verified",
        rate_source=rate_source,
    )


def test_item_cost_calculation() -> None:
    assert calculate_item_cost(12.5, 80) == 1000


def test_invalid_item_quantity_or_rate_is_rejected() -> None:
    with pytest.raises(BoqValidationError):
        calculate_item_cost(-1, 100)
    with pytest.raises(MissingRateError):
        calculate_item_cost(10, -1)


def test_missing_rate_is_reported() -> None:
    with pytest.raises(MissingRateError, match="wall-1"):
        calculate_costs((make_item(rate=0),))


def test_missing_rate_can_be_included_without_fabricating_cost() -> None:
    result = calculate_costs(
        (make_item(rate=0),),
        allow_missing_rates=True,
    )

    assert result.subtotal == 0
    assert result.grand_total == 0
    assert result.missing_rate_item_ids == ("wall-1",)


def test_waste_contingency_and_tax_are_applied_in_sequence() -> None:
    result = calculate_costs(
        (make_item(rate=100, quantity=10),),
        waste_percent=10,
        contingency_percent=5,
        tax_percent=18,
    )

    assert result.subtotal == 1000
    assert result.waste_amount == 100
    assert result.contingency_amount == 55
    assert result.tax_amount == 207.9
    assert result.grand_total == pytest.approx(1362.9)
    assert result.currency == "INR"


@pytest.mark.parametrize("percentage", [-1, float("inf"), "10"])
def test_invalid_cost_percentages_are_rejected(percentage) -> None:
    with pytest.raises(BoqValidationError):
        calculate_costs(
            (make_item(rate=100),),
            waste_percent=percentage,
        )
