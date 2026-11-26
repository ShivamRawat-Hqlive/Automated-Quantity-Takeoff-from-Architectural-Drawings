import pytest

from boq.boq_generator import CustomItem, generate_boq
from measurement.quantity_calculator import (
    QuantityResult,
    QuantitySummary,
)
from utils.exceptions import BoqValidationError


def create_quantity_result(
    *,
    verified_wall: float = 10,
    estimated_wall: float = 4,
    verified_room: float = 25,
    estimated_room: float = 5,
    verified_doors: int = 2,
    unverified_doors: int = 3,
    verified_windows: int = 1,
    unverified_windows: int = 2,
) -> QuantityResult:
    from measurement.quantity_calculator import RoomQuantity, WallQuantity

    walls = ()
    if verified_wall >= 0:
        walls += (
            WallQuantity(
                id="wall-verified",
                length_px=100,
                length_m=verified_wall,
                thickness_px=10,
                thickness_m=1,
                status="verified",
                quantity_type="verified",
            ),
        )
    if estimated_wall >= 0:
        walls += (
            WallQuantity(
                id="wall-estimated",
                length_px=40,
                length_m=estimated_wall,
                thickness_px=None,
                thickness_m=None,
                status="unverified",
                quantity_type="estimated",
            ),
        )
    rooms = ()
    if verified_room >= 0:
        rooms += (
            RoomQuantity(
                id="room-verified",
                area_px2=2500,
                area_m2=verified_room,
                perimeter_px=200,
                perimeter_m=20,
                status="verified",
                quantity_type="verified",
            ),
        )
    if estimated_room >= 0:
        rooms += (
            RoomQuantity(
                id="room-estimated",
                area_px2=500,
                area_m2=estimated_room,
                perimeter_px=100,
                perimeter_m=10,
                status="unverified",
                quantity_type="estimated",
            ),
        )
    summary = QuantitySummary(
        estimated_wall_length_m=estimated_wall,
        verified_wall_length_m=verified_wall,
        manual_wall_length_m=0,
        unverified_wall_count=1,
        estimated_room_area_m2=estimated_room,
        verified_room_area_m2=verified_room,
        manual_room_area_m2=0,
        floor_area_m2=verified_room,
        manual_floor_area_m2=0,
        verified_door_count=verified_doors,
        verified_window_count=verified_windows,
        manual_door_count=0,
        manual_window_count=0,
        unverified_door_count=unverified_doors,
        unverified_window_count=unverified_windows,
    )
    return QuantityResult(walls=walls, rooms=rooms, summary=summary)


def test_verified_quantities_are_default() -> None:
    result = generate_boq(create_quantity_result())
    names = {item.name for item in result}

    assert "Wall" in names
    assert "Floor area" in names
    assert "Door" in names
    assert "Window" in names
    assert "Wall (estimated)" not in names
    assert "Floor area (estimated)" not in names
    assert "Door (estimated)" not in names
    assert "Window (estimated)" not in names


def test_estimated_quantities_are_separate_when_requested() -> None:
    result = generate_boq(
        create_quantity_result(),
        include_estimated=True,
    )
    names = {item.name for item in result}

    assert "Wall (estimated)" in names
    assert "Floor area (estimated)" in names
    assert "Door (estimated)" in names
    assert "Window (estimated)" in names


def test_custom_and_fixture_items_are_supported() -> None:
    result = generate_boq(
        create_quantity_result(),
        custom_items=(
            CustomItem(
                item_id="fixture-1",
                name="Fixture",
                description="Manually entered fixture",
                quantity=4,
                unit="nos",
                rate=125,
            ),
        ),
    )

    fixture = next(item for item in result if item.item_id == "fixture-1")
    assert fixture.quantity == 4
    assert fixture.unit == "nos"
    assert fixture.total == 500


def test_duplicate_boq_items_are_rejected() -> None:
    with pytest.raises(BoqValidationError, match="Duplicate"):
        generate_boq(
            create_quantity_result(),
            custom_items=(
                CustomItem(
                    item_id="wall-1",
                    name="Wall",
                    description="Duplicate wall name",
                    quantity=1,
                    unit="m",
                    rate=100,
                ),
            ),
        )


def test_invalid_custom_quantity_is_rejected() -> None:
    with pytest.raises(BoqValidationError, match="quantity"):
        generate_boq(
            create_quantity_result(),
            custom_items=(
                CustomItem(
                    item_id="fixture-negative",
                    name="Fixture",
                    description="Invalid fixture quantity",
                    quantity=-1,
                    unit="nos",
                    rate=10,
                ),
            ),
        )
