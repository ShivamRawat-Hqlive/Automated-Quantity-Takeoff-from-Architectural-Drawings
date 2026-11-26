"""Independent raster drawing annotation for Phase 3-6 outputs."""

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from detection.detector import DetectionRecord
from measurement.quantity_calculator import QuantityResult
from measurement.scale_calibration import ScaleCalibration

Point = tuple[float, float]
AnnotationStatus = Literal["verified", "unverified", "rejected", "manual"]
ElementVisibility = Literal["wall", "room", "door", "window"]


@dataclass(frozen=True)
class AnnotationOptions:
    """Visibility and label controls for raster annotation."""

    show_walls: bool = True
    show_rooms: bool = True
    show_doors: bool = True
    show_windows: bool = True
    show_ids: bool = True
    show_measurements: bool = True


@dataclass(frozen=True)
class AnnotationSummary:
    """Counts based on records passed to the renderer."""

    verified: int
    unverified: int
    rejected: int
    manual: int
    visible: int
    walls: int
    rooms: int
    doors: int
    windows: int


@dataclass(frozen=True)
class AnnotationResult:
    """Annotated image and export metadata."""

    image: Image.Image
    summary: AnnotationSummary
    width: int
    height: int
    coordinate_frame: str


STATUS_COLORS = {
    "verified": (18, 150, 75),
    "unverified": (255, 165, 0),
    "rejected": (220, 220, 220),
    "manual": (55, 120, 220),
}

CLASS_COLORS = {
    "wall": (255, 215, 0),
    "room": (128, 50, 255),
    "door": (220, 60, 60),
    "window": (40, 180, 220),
}


def _validate_raster(image: Image.Image) -> tuple[int, int]:
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("Annotated raster dimensions must be positive.")
    return width, height


def _validate_geometry(
    record: DetectionRecord,
    width: int,
    height: int,
) -> tuple[Point, ...]:
    if not record.geometry:
        return ()
    validated: list[Point] = []
    for point in record.geometry:
        x, y = float(point[0]), float(point[1])
        if not np.isfinite(x) or not np.isfinite(y):
            raise ValueError(f"{record.id} contains a non-finite coordinate.")
        if x < 0 or y < 0 or x > width or y > height:
            raise ValueError(
                f"{record.id} geometry is outside the source raster."
            )
        validated.append((x, y))
    return tuple(validated)


def _validate_bounding_box(
    record: DetectionRecord,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if len(record.bbox) != 4:
        raise ValueError(f"{record.id} has an invalid bounding box.")
    x0, y0, x1, y1 = (float(value) for value in record.bbox)
    if not all(np.isfinite(value) for value in (x0, y0, x1, y1)):
        raise ValueError(f"{record.id} has a non-finite bounding box.")
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height or x1 < x0 or y1 < y0:
        raise ValueError(f"{record.id} bounding box is outside the source raster.")
    return round(x0), round(y0), round(x1), round(y1)


def _record_status(
    record: DetectionRecord,
    verified_ids: tuple[str, ...],
    rejected_ids: tuple[str, ...],
    manual_ids: tuple[str, ...],
) -> AnnotationStatus:
    if record.id in rejected_ids:
        return "rejected"
    if record.id in manual_ids:
        return "manual"
    if record.id in verified_ids:
        return "verified"
    return "unverified"


def _wall_measurement(
    record: DetectionRecord,
    quantity_result: QuantityResult | None,
) -> str | None:
    if quantity_result is None:
        return None
    for wall in quantity_result.walls:
        if wall.id == record.id:
            if wall.length_m is not None:
                return f"{wall.length_m:.3f} m"
            return f"{wall.length_px:.1f} px"
    return None


def _room_measurement(
    record: DetectionRecord,
    quantity_result: QuantityResult | None,
) -> str | None:
    if quantity_result is None:
        return None
    for room in quantity_result.rooms:
        if room.id == record.id:
            if room.area_m2 is not None:
                return f"{room.area_m2:.3f} m2"
            return f"{room.area_px2:.1f} px2"
    return None


def create_annotated_drawing(
    original: Image.Image,
    records: tuple[DetectionRecord, ...],
    *,
    quantity_result: QuantityResult | None = None,
    calibration: ScaleCalibration | None = None,
    verified_ids: tuple[str, ...] = (),
    rejected_ids: tuple[str, ...] = (),
    manual_ids: tuple[str, ...] = (),
    options: AnnotationOptions | None = None,
) -> AnnotationResult:
    """Create a copy with status-colored elements and labels in raster pixels."""
    width, height = _validate_raster(original)
    options = options or AnnotationOptions()

    if calibration is not None:
        if (
            calibration.source_width != width
            or calibration.source_height != height
            or calibration.coordinate_frame != "source image pixels; origin at top-left"
        ):
            raise ValueError(
                "Calibration does not match the source raster coordinate frame."
            )

    raster = np.asarray(original.convert("RGB")).copy()
    counts = {"verified": 0, "unverified": 0, "rejected": 0, "manual": 0}
    visible_counts = {"wall": 0, "room": 0, "door": 0, "window": 0}

    for record in records:
        status = _record_status(record, verified_ids, rejected_ids, manual_ids)
        counts[status] += 1
        visible = {
            "wall": options.show_walls,
            "room": options.show_rooms,
            "door": options.show_doors,
            "window": options.show_windows,
        }[record.element_class]
        if not visible:
            continue

        geometry = _validate_geometry(record, width, height)
        if not geometry:
            continue
        visible_counts[record.element_class] += 1
        status_color = STATUS_COLORS[status]
        class_color = CLASS_COLORS[record.element_class]
        points = np.asarray(
            [(round(point[0]), round(point[1])) for point in geometry],
            dtype=np.int32,
        ).reshape(-1, 1, 2)

        if record.element_class == "wall":
            cv2.polylines(raster, [points], False, status_color, 3)
        elif record.element_class == "room":
            cv2.polylines(raster, [points], True, status_color, 3)
        else:
            x0, y0, x1, y1 = _validate_bounding_box(record, width, height)
            cv2.rectangle(
                raster,
                (round(x0), round(y0)),
                (round(x1), round(y1)),
                status_color,
                2,
            )

        label_parts = [record.id] if options.show_ids else []
        if options.show_measurements:
            if record.element_class == "wall":
                measurement = _wall_measurement(record, quantity_result)
            elif record.element_class == "room":
                measurement = _room_measurement(record, quantity_result)
            else:
                measurement = None
            if measurement:
                label_parts.append(measurement)

        if label_parts:
            x = int(max(0, min(width - 1, geometry[0][0])))
            y = int(max(12, min(height - 1, geometry[0][1] - 5)))
            label = " · ".join(label_parts)
            cv2.putText(
                raster,
                label,
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                status_color,
                1,
                cv2.LINE_AA,
            )

    legend_items = (
        ("Verified", STATUS_COLORS["verified"]),
        ("Unverified", STATUS_COLORS["unverified"]),
        ("Rejected", STATUS_COLORS["rejected"]),
        ("Manual", STATUS_COLORS["manual"]),
    )
    legend_y = 18
    cv2.rectangle(raster, (8, 4), (170, 68), (245, 245, 245), -1)
    cv2.rectangle(raster, (8, 4), (170, 68), (40, 40, 40), 1)
    for index, (label, color) in enumerate(legend_items):
        y = legend_y + index * 14
        cv2.rectangle(raster, (14, y - 8), (26, y + 2), color, -1)
        cv2.putText(
            raster,
            label,
            (32, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )

    summary = AnnotationSummary(
        verified=counts["verified"],
        unverified=counts["unverified"],
        rejected=counts["rejected"],
        manual=counts["manual"],
        visible=sum(visible_counts.values()),
        walls=visible_counts["wall"],
        rooms=visible_counts["room"],
        doors=visible_counts["door"],
        windows=visible_counts["window"],
    )
    return AnnotationResult(
        image=Image.fromarray(raster),
        summary=summary,
        width=width,
        height=height,
        coordinate_frame="source image pixels; origin at top-left",
    )


def export_annotated_png(annotation: AnnotationResult) -> bytes:
    """Encode an annotated copy as PNG without changing the source drawing."""
    output = BytesIO()
    annotation.image.save(output, format="PNG")
    return output.getvalue()
