"""Shared records and helpers for rule-based element candidate detectors."""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from processing.image_preprocessor import ImageAnalysis

ElementClass = Literal["wall", "room", "door", "window"]
VerificationStatus = Literal["unverified", "verified"]
Point = tuple[float, float]
BoundingBox = tuple[float, float, float, float]
MetadataValue = str | int | float | bool | None


@dataclass(frozen=True)
class DetectionRecord:
    """A geometric candidate; candidates remain unverified until reviewed."""

    id: str
    element_class: ElementClass
    geometry: tuple[Point, ...]
    bbox: BoundingBox
    confidence: float | None
    detection_method: str
    verification_status: VerificationStatus
    metadata: tuple[tuple[str, MetadataValue], ...]


def create_record(
    *,
    record_id: str,
    element_class: ElementClass,
    geometry: tuple[Point, ...],
    confidence: float | None,
    detection_method: str,
    metadata: tuple[tuple[str, MetadataValue], ...] = (),
) -> DetectionRecord:
    """Create a candidate record with a bounding box derived from its geometry."""
    if not geometry:
        raise ValueError("Candidate geometry must contain at least one point.")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ValueError("confidence must be between zero and one.")

    xs = [point[0] for point in geometry]
    ys = [point[1] for point in geometry]
    return DetectionRecord(
        id=record_id,
        element_class=element_class,
        geometry=geometry,
        bbox=(min(xs), min(ys), max(xs), max(ys)),
        confidence=confidence,
        detection_method=detection_method,
        verification_status="unverified",
        metadata=metadata,
    )


def draw_candidate_overlay(
    image: Image.Image,
    records: tuple[DetectionRecord, ...],
) -> Image.Image:
    """Return a copy of the source image with unverified candidates outlined."""
    overlay = np.asarray(image.convert("RGB")).copy()
    colors: dict[ElementClass, tuple[int, int, int]] = {
        "wall": (0, 220, 255),
        "room": (255, 190, 0),
        "door": (255, 60, 60),
        "window": (220, 80, 255),
    }

    for record in records:
        points = np.asarray(
            [(round(x), round(y)) for x, y in record.geometry],
            dtype=np.int32,
        ).reshape(-1, 1, 2)
        color = colors[record.element_class]
        cv2.polylines(
            overlay,
            [points],
            isClosed=record.element_class == "room",
            color=color,
            thickness=2,
        )
        x, y = points[0, 0]
        cv2.putText(
            overlay,
            f"{record.id} ?",
            (int(x), max(12, int(y) - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )
    return Image.fromarray(overlay)


def run_all_detectors(
    analysis: ImageAnalysis,
) -> tuple[DetectionRecord, ...]:
    """Run each conservative rule-based detector over one Phase 3 result."""
    from detection.door_detector import detect_doors
    from detection.room_detector import detect_rooms
    from detection.wall_detector import detect_walls
    from detection.window_detector import detect_windows

    return (
        detect_walls(analysis)
        + detect_rooms(analysis)
        + detect_doors(analysis)
        + detect_windows(analysis)
    )
