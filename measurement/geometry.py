"""Validated pixel-space line and polygon geometry."""

from math import hypot, isfinite

from detection.detector import DetectionRecord
from measurement.scale_calibration import ScaleCalibration
from utils.exceptions import MeasurementValidationError

Point = tuple[float, float]


def _validate_point(point: Point) -> Point:
    if (
        not isinstance(point, tuple)
        or len(point) != 2
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            for value in point
        )
    ):
        raise MeasurementValidationError("Geometry contains an invalid point.")
    return float(point[0]), float(point[1])


def line_length_px(start: Point, end: Point) -> float:
    """Calculate Euclidean length for a validated two-point line."""
    start = _validate_point(start)
    end = _validate_point(end)
    length = hypot(end[0] - start[0], end[1] - start[1])
    if length <= 0:
        raise MeasurementValidationError("A line must have distinct endpoints.")
    return length


def polygon_area_px2(polygon: tuple[Point, ...]) -> float:
    """Calculate signed polygon area magnitude using the shoelace formula."""
    validated = validate_polygon(polygon)
    twice_area = sum(
        validated[index][0] * validated[(index + 1) % len(validated)][1]
        - validated[(index + 1) % len(validated)][0] * validated[index][1]
        for index in range(len(validated))
    )
    area = abs(twice_area) / 2
    if area <= 0:
        raise MeasurementValidationError("Polygon area must be greater than zero.")
    return area


def polygon_perimeter_px(polygon: tuple[Point, ...]) -> float:
    """Calculate perimeter for a closed, validated polygon."""
    validated = validate_polygon(polygon)
    perimeter = sum(
        line_length_px(
            validated[index],
            validated[(index + 1) % len(validated)],
        )
        for index in range(len(validated))
    )
    return perimeter


def validate_polygon(polygon: tuple[Point, ...]) -> tuple[Point, ...]:
    """Reject incomplete, duplicate, and repeated-vertex polygon inputs."""
    if not isinstance(polygon, tuple) or len(polygon) < 3:
        raise MeasurementValidationError(
            "A room polygon must contain at least three points."
        )
    validated = tuple(_validate_point(point) for point in polygon)

    if validated[0] == validated[-1]:
        raise MeasurementValidationError(
            "A room polygon must not repeat its closing point."
        )
    unique = set(validated)
    if len(unique) != len(validated):
        raise MeasurementValidationError(
            "A room polygon contains duplicate vertices."
        )
    return validated


def deduplicate_geometry(records: tuple[DetectionRecord, ...]) -> tuple[DetectionRecord, ...]:
    """Remove exact and reversed or cyclic duplicate record geometries."""
    unique: list[DetectionRecord] = []
    seen: set[tuple[tuple[float, float], ...]] = set()
    for record in records:
        geometry = tuple(
            (round(float(point[0]), 6), round(float(point[1]), 6))
            for point in record.geometry
        )
        if len(geometry) == 2:
            canonical = tuple(sorted((geometry[0], geometry[1])))
        else:
            try:
                polygon = validate_polygon(geometry)
            except MeasurementValidationError:
                continue
            rotations = [polygon[index:] + polygon[:index] for index in range(len(polygon))]
            reversed_polygon = tuple(reversed(polygon))
            rotations += [
                reversed_polygon[index:] + reversed_polygon[:index]
                for index in range(len(reversed_polygon))
            ]
            canonical = min(rotations)
        key = (record.element_class,) + canonical
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return tuple(unique)


def filter_valid_room_records(
    records: tuple[DetectionRecord, ...],
    *,
    pixel_area_tolerance: float = 1,
) -> tuple[DetectionRecord, ...]:
    """Reject nested/duplicate room polygons and incomplete room contours."""
    room_records = tuple(record for record in records if record.element_class == "room")
    valid: list[DetectionRecord] = []
    for record in room_records:
        try:
            polygon_area_px2(record.geometry)
            polygon_perimeter_px(record.geometry)
        except MeasurementValidationError:
            continue
        valid.append(record)

    outermost: list[DetectionRecord] = []
    for record in valid:
        area = polygon_area_px2(record.geometry)
        x0, y0, x1, y1 = record.bbox
        nested = False
        for other in valid:
            if other.id == record.id:
                continue
            other_area = polygon_area_px2(other.geometry)
            ox0, oy0, ox1, oy1 = other.bbox
            inside_outer = (
                ox0 <= x0
                and oy0 <= y0
                and ox1 >= x1
                and oy1 >= y1
                and other_area >= area + pixel_area_tolerance
            )
            if inside_outer:
                nested = True
                break
        if not nested:
            outermost.append(record)
    return deduplicate_geometry(tuple(outermost))


def pixel_length_to_metre(length_px: float, calibration: ScaleCalibration) -> float:
    """Convert a pixel length using one validated raster calibration."""
    if not isfinite(length_px) or length_px <= 0:
        raise MeasurementValidationError("Pixel length must be finite and positive.")
    return length_px * calibration.metres_per_pixel


def pixel_area_to_square_metre(area_px2: float, calibration: ScaleCalibration) -> float:
    """Convert pixel area with square metres-per-pixel-squared."""
    if not isfinite(area_px2) or area_px2 < 0:
        raise MeasurementValidationError("Pixel area must be finite and non-negative.")
    return area_px2 * calibration.metres_per_pixel**2
