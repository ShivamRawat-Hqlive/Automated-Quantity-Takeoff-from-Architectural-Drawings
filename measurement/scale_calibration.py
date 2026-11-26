"""Pixel-to-real-world scale calibration with explicit coordinate metadata."""

from dataclasses import dataclass
from math import hypot, isfinite

from utils.exceptions import MeasurementValidationError

Point = tuple[float, float]
UNIT_TO_METRES = {
    "m": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "ft": 0.3048,
    "feet": 0.3048,
    "foot": 0.3048,
}


@dataclass(frozen=True)
class ScaleCalibration:
    """One recalibratable scale tied to a named source raster."""

    point_1: Point
    point_2: Point
    known_distance: float
    known_unit: str
    known_distance_metres: float
    pixel_distance: float
    pixels_per_metre: float
    metres_per_pixel: float
    source_width: int
    source_height: int
    coordinate_frame: str


def known_distance_to_metres(distance: float, unit: str) -> float:
    """Convert m, cm, mm, or feet to metres."""
    if not isinstance(distance, (int, float)) or isinstance(distance, bool):
        raise MeasurementValidationError("Known distance must be numeric.")
    if not isfinite(float(distance)) or float(distance) <= 0:
        raise MeasurementValidationError("Known distance must be finite and positive.")

    normalized_unit = unit.strip().lower()
    if normalized_unit not in UNIT_TO_METRES:
        raise MeasurementValidationError(
            "Known-distance unit must be m, cm, mm, or feet."
        )
    metres = float(distance) * UNIT_TO_METRES[normalized_unit]
    if metres <= 0:
        raise MeasurementValidationError("Known distance must be greater than zero.")
    return metres


def calibrate_scale(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    known_distance: float,
    known_unit: str,
    *,
    source_width: int,
    source_height: int,
    coordinate_frame: str,
) -> ScaleCalibration:
    """Calibrate two image-pixel points against one real-world distance."""
    values = (x1, y1, x2, y2)
    if any(
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(float(value))
        for value in values
    ):
        raise MeasurementValidationError(
            "Reference-point coordinates must be finite numbers."
        )
    if not isinstance(source_width, int) or not isinstance(source_height, int):
        raise MeasurementValidationError("Source raster dimensions must be integers.")
    if source_width <= 0 or source_height <= 0:
        raise MeasurementValidationError("Source raster dimensions must be positive.")

    point_1 = (float(x1), float(y1))
    point_2 = (float(x2), float(y2))
    if not (
        0 <= point_1[0] <= source_width
        and 0 <= point_1[1] <= source_height
        and 0 <= point_2[0] <= source_width
        and 0 <= point_2[1] <= source_height
    ):
        raise MeasurementValidationError(
            "Reference points must lie inside the source raster."
        )

    pixel_distance = hypot(point_2[0] - point_1[0], point_2[1] - point_1[1])
    if pixel_distance <= 0:
        raise MeasurementValidationError(
            "Reference points must not describe the same pixel."
        )

    metres = known_distance_to_metres(known_distance, known_unit)
    pixels_per_metre = pixel_distance / metres
    if not isfinite(pixels_per_metre) or pixels_per_metre <= 0:
        raise MeasurementValidationError("Calibration produced an invalid scale.")

    return ScaleCalibration(
        point_1=point_1,
        point_2=point_2,
        known_distance=float(known_distance),
        known_unit=known_unit.strip().lower(),
        known_distance_metres=metres,
        pixel_distance=pixel_distance,
        pixels_per_metre=pixels_per_metre,
        metres_per_pixel=1 / pixels_per_metre,
        source_width=source_width,
        source_height=source_height,
        coordinate_frame=coordinate_frame.strip(),
    )


def validate_calibration_for_raster(
    calibration: ScaleCalibration,
    *,
    source_width: int,
    source_height: int,
    coordinate_frame: str,
) -> None:
    """Reject measurements when the calibration belongs to another raster frame."""
    if (
        calibration.source_width != source_width
        or calibration.source_height != source_height
        or calibration.coordinate_frame != coordinate_frame
    ):
        raise MeasurementValidationError(
            "Calibration raster dimensions or coordinate frame do not match "
            "the current drawing."
        )
