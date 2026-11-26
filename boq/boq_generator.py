"""Generate BoQ records from Phase 5 quantity outputs."""

from dataclasses import dataclass

from measurement.quantity_calculator import QuantityResult
from utils.exceptions import BoqValidationError


@dataclass(frozen=True)
class BoQItem:
    item_id: str
    name: str
    description: str
    quantity: float
    unit: str
    rate: float
    total: float
    status: str
    rate_source: str


@dataclass(frozen=True)
class CustomItem:
    item_id: str
    name: str
    description: str
    quantity: float
    unit: str
    rate: float
    status: str = "manual"
    rate_source: str = "user-entered"


def _validate_quantity(quantity: float) -> float:
    if (
        not isinstance(quantity, (int, float))
        or isinstance(quantity, bool)
        or quantity < 0
    ):
        raise BoqValidationError("BoQ quantity must be non-negative.")
    return float(quantity)


def generate_boq(
    quantity_result: QuantityResult,
    *,
    custom_items: tuple[CustomItem, ...] = (),
    include_estimated: bool = False,
    currency: str = "INR",
) -> tuple[BoQItem, ...]:
    """Generate default verified quantities plus optional separate custom items."""
    items: list[BoQItem] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    normalized_currency = currency.strip().upper()
    if not normalized_currency:
        raise BoqValidationError("Currency is required.")

    def add(
        item_id: str,
        name: str,
        description: str,
        quantity: float,
        unit: str,
        rate: float,
        status: str,
        rate_source: str,
    ) -> None:
        normalized_id = item_id.strip()
        normalized_name = name.strip().lower()
        if not normalized_id or not name.strip():
            raise BoqValidationError("BoQ item ID and name are required.")
        if normalized_id in seen_ids or normalized_name in seen_names:
            raise BoqValidationError(
                f"Duplicate BoQ item ID or name: {item_id}"
            )
        validated_quantity = _validate_quantity(quantity)
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate < 0:
            raise BoqValidationError("BoQ rate must be non-negative.")
        seen_ids.add(normalized_id)
        seen_names.add(normalized_name)
        items.append(
            BoQItem(
                item_id=normalized_id,
                name=name,
                description=description,
                quantity=validated_quantity,
                unit=unit,
                rate=float(rate),
                total=validated_quantity * float(rate),
                status=status,
                rate_source=rate_source,
            )
        )

    verified_wall_m = sum(
        wall.length_m
        for wall in quantity_result.walls
        if wall.status == "verified" and wall.length_m is not None
    )
    if verified_wall_m > 0:
        add(
            "verified-wall-length",
            "Wall",
            "Aggregated verified wall segment length",
            verified_wall_m,
            "m",
            0,
            "verified",
            "missing",
        )
    if include_estimated:
        estimated_wall_m = sum(
            wall.length_m
            for wall in quantity_result.walls
            if wall.status == "unverified" and wall.length_m is not None
        )
        if estimated_wall_m > 0:
            add(
                "estimated-wall-length",
                "Wall (estimated)",
                "Aggregated unverified wall segment length",
                estimated_wall_m,
                "m",
                0,
                "unverified",
                "missing",
            )

    verified_room_m2 = sum(
        room.area_m2
        for room in quantity_result.rooms
        if room.status == "verified" and room.area_m2 is not None
    )
    if verified_room_m2 > 0:
        add(
            "verified-floor-area",
            "Floor area",
            "Aggregated verified room/floor polygon area",
            verified_room_m2,
            "m2",
            0,
            "verified",
            "missing",
        )
    if include_estimated:
        estimated_room_m2 = sum(
            room.area_m2
            for room in quantity_result.rooms
            if room.status == "unverified" and room.area_m2 is not None
        )
        if estimated_room_m2 > 0:
            add(
                "estimated-floor-area",
                "Floor area (estimated)",
                "Aggregated unverified room/floor polygon area",
                estimated_room_m2,
                "m2",
                0,
                "unverified",
                "missing",
            )

    summary = quantity_result.summary
    if summary.verified_door_count > 0:
        add("verified-door-count", "Door", "Verified door count", summary.verified_door_count, "nos", 0, "verified", "missing")
    if include_estimated and summary.unverified_door_count > 0:
        add("estimated-door-count", "Door (estimated)", "Unverified door candidate count", summary.unverified_door_count, "nos", 0, "unverified", "missing")
    if summary.verified_window_count > 0:
        add("verified-window-count", "Window", "Verified window count", summary.verified_window_count, "nos", 0, "verified", "missing")
    if include_estimated and summary.unverified_window_count > 0:
        add("estimated-window-count", "Window (estimated)", "Unverified window candidate count", summary.unverified_window_count, "nos", 0, "unverified", "missing")
    if summary.manual_door_count > 0:
        add("manual-door-count", "Door (manual)", "Manually entered door count", summary.manual_door_count, "nos", 0, "manual", "missing")
    if summary.manual_window_count > 0:
        add("manual-window-count", "Window (manual)", "Manually entered window count", summary.manual_window_count, "nos", 0, "manual", "missing")

    for custom in custom_items:
        add(
            custom.item_id,
            custom.name,
            custom.description,
            custom.quantity,
            custom.unit,
            custom.rate,
            custom.status,
            custom.rate_source,
        )
    return tuple(items)
