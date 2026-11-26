import pytest

from measurement.geometry import (
    deduplicate_geometry,
    line_length_px,
    pixel_area_to_square_metre,
    pixel_length_to_metre,
    polygon_area_px2,
    polygon_perimeter_px,
    validate_polygon,
)
from measurement.scale_calibration import calibrate_scale
from detection.detector import create_record
from utils.exceptions import MeasurementValidationError


def test_horizontal_vertical_and_diagonal_lengths() -> None:
    assert line_length_px((0, 0), (10, 0)) == 10
    assert line_length_px((0, 0), (0, 7)) == 7
    assert line_length_px((0, 0), (3, 4)) == 5


def test_rectangle_and_irregular_polygon_measurements() -> None:
    rectangle = ((0, 0), (10, 0), (10, 5), (0, 5))
    irregular = ((0, 0), (4, 0), (6, 3), (2, 5), (-1, 2))

    assert polygon_area_px2(rectangle) == 50
    assert polygon_perimeter_px(rectangle) == 30
    assert polygon_area_px2(irregular) > 0
    assert polygon_perimeter_px(irregular) > 0


@pytest.mark.parametrize(
    "polygon",
    [((0, 0), (1, 1)), ((0, 0), (1, 0), (1, 0))],
)
def test_invalid_or_duplicate_polygons(polygon: tuple) -> None:
    with pytest.raises(MeasurementValidationError):
        validate_polygon(polygon)


def test_closed_polygon_must_not_repeat_closing_point() -> None:
    with pytest.raises(MeasurementValidationError, match="closing point"):
        validate_polygon(((0, 0), (1, 0), (1, 1), (0, 0)))


def test_pixel_and_real_world_conversion() -> None:
    scale = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=100,
        source_height=100,
        coordinate_frame="source pixels",
    )
    assert pixel_length_to_metre(100, scale) == 1
    assert pixel_area_to_square_metre(10000, scale) == 1


def test_duplicate_line_and_reversed_polygon_geometries_are_removed() -> None:
    line_a = create_record(
        record_id="wall-a",
        element_class="wall",
        geometry=((0, 0), (10, 0)),
        confidence=None,
        detection_method="test",
    )
    line_b = create_record(
        record_id="wall-b",
        element_class="wall",
        geometry=((10, 0), (0, 0)),
        confidence=None,
        detection_method="test",
    )
    room_a = create_record(
        record_id="room-a",
        element_class="room",
        geometry=((0, 0), (10, 0), (10, 10), (0, 10)),
        confidence=None,
        detection_method="test",
    )
    room_b = create_record(
        record_id="room-b",
        element_class="room",
        geometry=((0, 10), (10, 10), (10, 0), (0, 0)),
        confidence=None,
        detection_method="test",
    )

    deduplicated = deduplicate_geometry((line_a, line_b, room_a, room_b))
    assert {record.element_class for record in deduplicated} == {"wall", "room"}
    assert len(deduplicated) == 2
