import pytest

from measurement.scale_calibration import (
    calibrate_scale,
    known_distance_to_metres,
    validate_calibration_for_raster,
)
from utils.exceptions import MeasurementValidationError


def test_calibrate_horizontal_reference_points() -> None:
    scale = calibrate_scale(
        10,
        20,
        110,
        20,
        2,
        "m",
        source_width=200,
        source_height=100,
        coordinate_frame="source pixels",
    )

    assert scale.pixel_distance == 100
    assert scale.pixels_per_metre == 50
    assert scale.metres_per_pixel == 0.02
    assert scale.known_distance_metres == 2


@pytest.mark.parametrize(
    ("unit", "metres"),
    [("m", 3), ("cm", 0.03), ("mm", 0.003), ("ft", 0.9144), ("feet", 0.9144)],
)
def test_supported_distance_units(unit: str, metres: float) -> None:
    if unit == "cm":
        assert known_distance_to_metres(3, "cm") == pytest.approx(0.03)
    elif unit == "mm":
        assert known_distance_to_metres(3, "mm") == pytest.approx(0.003)
    else:
        assert known_distance_to_metres(3, unit) == pytest.approx(metres)


@pytest.mark.parametrize(
    ("known_distance", "unit"),
    [(0, "m"), (-1, "m"), (float("inf"), "cm"), (1, "inch")],
)
def test_invalid_calibration_inputs(known_distance: float, unit: str) -> None:
    with pytest.raises(MeasurementValidationError):
        calibrate_scale(
            0,
            0,
            10,
            0,
            known_distance,
            unit,
            source_width=100,
            source_height=100,
            coordinate_frame="source pixels",
        )


def test_same_point_reference_is_invalid() -> None:
    with pytest.raises(MeasurementValidationError, match="same pixel"):
        calibrate_scale(
            10,
            10,
            10,
            10,
            1,
            "m",
            source_width=100,
            source_height=100,
            coordinate_frame="source pixels",
        )


def test_reference_outside_raster_is_invalid() -> None:
    with pytest.raises(MeasurementValidationError, match="inside"):
        calibrate_scale(
            -1,
            0,
            10,
            0,
            1,
            "m",
            source_width=100,
            source_height=100,
            coordinate_frame="source pixels",
        )


def test_recalibration_and_raster_frame_validation() -> None:
    first = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=100,
        source_height=100,
        coordinate_frame="source image pixels",
    )
    recalibrated = calibrate_scale(
        0,
        0,
        50,
        0,
        1,
        "m",
        source_width=100,
        source_height=100,
        coordinate_frame="source image pixels",
    )

    validate_calibration_for_raster(
        recalibrated,
        source_width=100,
        source_height=100,
        coordinate_frame="source image pixels",
    )
    assert recalibrated.pixels_per_metre == 50
    assert first.pixels_per_metre == 100

    with pytest.raises(MeasurementValidationError, match="do not match"):
        validate_calibration_for_raster(
            recalibrated,
            source_width=200,
            source_height=100,
            coordinate_frame="source image pixels",
        )
