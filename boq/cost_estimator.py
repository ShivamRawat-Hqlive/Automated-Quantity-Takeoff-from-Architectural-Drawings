"""Cost calculations for BoQ items."""

from dataclasses import dataclass
from math import isfinite

from boq.boq_generator import BoQItem
from utils.exceptions import MissingRateError, BoqValidationError


@dataclass(frozen=True)
class CostBreakdown:
    subtotal: float
    waste_amount: float
    contingency_amount: float
    tax_amount: float
    grand_total: float
    currency: str
    missing_rate_item_ids: tuple[str, ...]


def calculate_item_cost(quantity: float, rate: float) -> float:
    if (
        not isinstance(quantity, (int, float))
        or isinstance(quantity, bool)
        or not isfinite(float(quantity))
        or quantity < 0
    ):
        raise BoqValidationError("Item quantity must be finite and non-negative.")
    if (
        not isinstance(rate, (int, float))
        or isinstance(rate, bool)
        or not isfinite(float(rate))
        or rate < 0
    ):
        raise MissingRateError("Item rate must be finite and non-negative.")
    return float(quantity) * float(rate)


def calculate_costs(
    items: tuple[BoQItem, ...] | list[BoQItem],
    *,
    waste_percent: float = 0,
    contingency_percent: float = 0,
    tax_percent: float = 0,
    currency: str = "INR",
    allow_missing_rates: bool = False,
) -> CostBreakdown:
    """Calculate cost layers while making missing/zero rates explicit."""
    percentages = (waste_percent, contingency_percent, tax_percent)
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
        or value < 0
        for value in percentages
    ):
        raise BoqValidationError(
            "Waste, contingency, and tax percentages must be non-negative."
        )

    missing: list[str] = []
    subtotal = 0.0
    for item in items:
        if item.rate_source == "missing" or item.rate <= 0:
            missing.append(item.item_id)
        subtotal += calculate_item_cost(item.quantity, item.rate)

    if missing and not allow_missing_rates:
        raise MissingRateError(
            "Missing or zero rates prevent costing: " + ", ".join(missing)
        )

    waste_amount = subtotal * float(waste_percent) / 100
    subtotal_with_waste = subtotal + waste_amount
    contingency_amount = subtotal_with_waste * float(contingency_percent) / 100
    subtotal_with_contingency = subtotal_with_waste + contingency_amount
    tax_amount = subtotal_with_contingency * float(tax_percent) / 100
    grand_total = subtotal_with_contingency + tax_amount
    return CostBreakdown(
        subtotal=subtotal,
        waste_amount=waste_amount,
        contingency_amount=contingency_amount,
        tax_amount=tax_amount,
        grand_total=grand_total,
        currency=currency.strip().upper(),
        missing_rate_item_ids=tuple(missing),
    )
