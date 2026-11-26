import pytest

from detection.detector import create_record
from measurement.geometry import filter_valid_room_records
from measurement.quantity_calculator import calculate_quantities
from measurement.scale_calibration import calibrate_scale


def create_wall(record_id: str = "wall-1", geometry=None):
    return create_record(
        record_id=record_id,
        element_class="wall",
        geometry=geometry or ((0, 0), (100, 0)),
        confidence=None,
        detection_method="test",
        metadata=(("estimated_thickness_px", 10),),
    )


def create_room(record_id: str = "room-1", geometry=None):
    return create_record(
        record_id=record_id,
        element_class="room",
        geometry=geometry or ((0, 0), (100, 0), (100, 100), (0, 100)),
        confidence=None,
        detection_method="test",
        metadata=(("area_px2", 10000),),
    )


def test_uncalibrated_quantities_keep_pixel_values_without_real_units() -> None:
    result = calculate_quantities(
        (create_wall(), create_room()),
        calibration=None,
    )

    assert result.walls[0].length_m is None
    assert result.rooms[0].area_m2 is None
    assert result.summary.estimated_wall_length_m == 0
    assert result.summary.estimated_room_area_m2 == 0
    assert result.summary.unverified_wall_count == 1


def test_calibrated_wall_room_and_floor_quantities() -> None:
    scale = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=200,
        source_height=200,
        coordinate_frame="source pixels",
    )
    result = calculate_quantities(
        (create_wall(), create_room()),
        scale,
    )

    assert result.walls[0].length_m == pytest.approx(1)
    assert result.walls[0].thickness_m == pytest.approx(0.1)
    assert result.rooms[0].area_m2 == pytest.approx(1)
    assert result.rooms[0].perimeter_m == pytest.approx(4)
    assert result.summary.estimated_room_area_m2 == pytest.approx(1)
    assert result.summary.floor_area_m2 == 0


def test_verified_records_only_affect_verified_floor_and_counts() -> None:
    scale = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=200,
        source_height=200,
        coordinate_frame="source pixels",
    )
    door = create_record(
        record_id="door-1",
        element_class="door",
        geometry=((0, 0), (10, 0)),
        confidence=None,
        detection_method="test",
    )
    window = create_record(
        record_id="window-1",
        element_class="window",
        geometry=((0, 0), (10, 0)),
        confidence=None,
        detection_method="test",
    )
    result = calculate_quantities(
        (create_wall(), create_room(), door, window),
        scale,
        verified_record_ids=("room-1", "wall-1", "door-1"),
    )

    assert result.summary.verified_wall_length_m == pytest.approx(1)
    assert result.summary.verified_room_area_m2 == pytest.approx(1)
    assert result.summary.floor_area_m2 == pytest.approx(1)
    assert result.summary.verified_door_count == 1
    assert result.summary.verified_window_count == 0
    assert result.summary.unverified_door_count == 0
    assert result.summary.unverified_window_count == 1


def test_invalid_duplicate_nested_and_incomplete_rooms_are_filtered() -> None:
    outer = create_room(
        "room-outer",
        ((10, 10), (200, 10), (200, 200), (10, 200)),
    )
    nested = create_room(
        "room-inner",
        ((50, 50), (100, 50), (100, 100), (50, 100)),
    )
    duplicate = create_room(
        "room-duplicate",
        ((10, 200), (200, 200), (200, 10), (10, 10)),
    )
    incomplete = create_record(
        record_id="room-incomplete",
        element_class="room",
        geometry=((10, 10), (20, 10)),
        confidence=None,
        detection_method="test",
    )

    valid = filter_valid_room_records(
        (outer, nested, duplicate, incomplete)
    )

    assert [record.id for record in valid] == ["room-outer"]


def test_missing_scale_does_not_create_real_world_room_or_wall_values() -> None:
    result = calculate_quantities(
        (
            create_wall("wall-one"),
            create_room("room-one"),
            create_record(
                record_id="door-candidate",
                element_class="door",
                geometry=((0, 0), (10, 0)),
                confidence=None,
                detection_method="test",
            ),
        ),
        None,
    )

    assert all(wall.length_m is None for wall in result.walls)
    assert all(room.area_m2 is None for room in result.rooms)
    assert result.summary.verified_door_count == 0
    assert result.summary.unverified_door_count == 1
