"""Validated corrections for detection records without mutating originals."""

from dataclasses import replace
from math import isfinite

from detection.detector import DetectionRecord, ElementClass
from measurement.geometry import validate_polygon
from measurement.geometry import MeasurementValidationError
from utils.exceptions import VerificationValidationError


def validate_record_geometry(
    record: DetectionRecord,
    *,
    source_width: int,
    source_height: int,
) -> DetectionRecord:
    """Validate geometry and derived bbox against the source raster."""
    if source_width <= 0 or source_height <= 0:
        raise VerificationValidationError("Source raster dimensions must be positive.")
    if not record.id.strip():
        raise VerificationValidationError("Record ID is required.")
    if record.element_class not in {"wall", "room", "door", "window"}:
        raise VerificationValidationError("Unsupported element class.")
    if not record.geometry:
        raise VerificationValidationError("Geometry must contain at least one point.")

    validated: list[tuple[float, float]] = []
    for point in record.geometry:
        if not isinstance(point, tuple) or len(point) != 2:
            raise VerificationValidationError("Every geometry point needs x and y.")
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, ValueError) as exc:
            raise VerificationValidationError("Geometry coordinates must be numeric.") from exc
        if not isfinite(x) or not isfinite(y):
            raise VerificationValidationError("Geometry coordinates must be finite.")
        if x < 0 or y < 0 or x > source_width or y > source_height:
            raise VerificationValidationError(
                "Geometry lies outside the source raster."
            )
        validated.append((x, y))

    geometry = tuple(validated)
    if record.element_class == "wall" and len(geometry) != 2:
        raise VerificationValidationError("A wall record requires exactly two points.")
    if record.element_class in {"room"}:
        try:
            validate_polygon(geometry)
        except MeasurementValidationError as exc:
            raise VerificationValidationError(str(exc)) from exc
    if record.element_class in {"door", "window"}:
        x0 = min(point[0] for point in geometry)
        y0 = min(point[1] for point in geometry)
        x1 = max(point[0] for point in geometry)
        y1 = max(point[1] for point in geometry)
        if x1 == x0:
            x1 = x0 + 1
        if y1 == y0:
            y1 = y0 + 1
        if x0 < 0 or y0 < 0 or x1 > source_width or y1 > source_height or x1 <= x0 or y1 <= y0:
            raise VerificationValidationError(
                "Door/window bounding box is outside the source raster."
            )

    bbox = (
        min(point[0] for point in geometry),
        min(point[1] for point in geometry),
        max(point[0] for point in geometry),
        max(point[1] for point in geometry),
    )
    if record.element_class in {"door", "window"}:
        x0, y0, x1, y1 = bbox
        bbox = (
            x0,
            y0,
            x1 if x1 > x0 else x0 + 1,
            y1 if y1 > y0 else y0 + 1,
        )
    return replace(record, geometry=geometry, bbox=bbox)


def edit_record(
    record: DetectionRecord,
    *,
    element_class: ElementClass | None = None,
    geometry: tuple[tuple[float, float], ...] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    source_width: int,
    source_height: int,
) -> DetectionRecord:
    """Return a corrected copy; never mutate the supplied record."""
    corrected = replace(
        record,
        element_class=element_class or record.element_class,
        geometry=geometry if geometry is not None else record.geometry,
        bbox=bbox if bbox is not None else record.bbox,
    )
    return validate_record_geometry(
        corrected,
        source_width=source_width,
        source_height=source_height,
    )


def create_manual_record(
    record_id: str,
    element_class: ElementClass,
    geometry: tuple[tuple[float, float], ...],
    *,
    source_width: int,
    source_height: int,
    note: str = "",
) -> DetectionRecord:
    """Create an explicitly manual record without auto-verification."""
    record = DetectionRecord(
        id=record_id,
        element_class=element_class,
        geometry=geometry,
        bbox=(
            min(point[0] for point in geometry),
            min(point[1] for point in geometry),
            max(point[0] for point in geometry) + (1 if len({point[0] for point in geometry}) == 1 else 0),
            max(point[1] for point in geometry) + (1 if len({point[1] for point in geometry}) == 1 else 0),
        ),
        confidence=None,
        detection_method="manual user entry",
        verification_status="unverified",
        metadata=(("manual_entry", True), ("correction_note", note)),
    )
    return validate_record_geometry(
        record,
        source_width=source_width,
        source_height=source_height,
    )
