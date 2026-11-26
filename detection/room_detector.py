"""Conservative room-boundary candidates from morphology and contours."""

import cv2
import numpy as np

from detection.detector import DetectionRecord, create_record
from processing.image_preprocessor import ImageAnalysis


def detect_rooms(
    analysis: ImageAnalysis,
    *,
    minimum_area_px2: float = 1000,
    closing_kernel_size: int = 5,
) -> tuple[DetectionRecord, ...]:
    """Find enclosed room-like regions; returned polygons are unverified candidates."""
    if minimum_area_px2 <= 0:
        raise ValueError("minimum_area_px2 must be positive.")
    if (
        not isinstance(closing_kernel_size, int)
        or isinstance(closing_kernel_size, bool)
        or closing_kernel_size <= 0
        or closing_kernel_size % 2 == 0
    ):
        raise ValueError("closing_kernel_size must be a positive odd integer.")

    height, width = analysis.binary_threshold.shape
    wall_mask = cv2.bitwise_not(analysis.binary_threshold)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT,
        (closing_kernel_size, closing_kernel_size),
    )
    closed_wall_mask = cv2.morphologyEx(
        wall_mask,
        cv2.MORPH_CLOSE,
        kernel,
    )
    room_regions = cv2.bitwise_not(closed_wall_mask)
    contours, hierarchy = cv2.findContours(
        room_regions,
        cv2.RETR_CCOMP,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    if hierarchy is None:
        return ()

    candidates: list[tuple[tuple[int, int, int, int], np.ndarray, float, float]] = []
    image_area = width * height
    for contour_index, contour in enumerate(contours):
        if hierarchy[0, contour_index, 3] != -1:
            continue
        area = float(cv2.contourArea(contour))
        if area < minimum_area_px2 or area >= image_area * 0.95:
            continue
        x, y, box_width, box_height = cv2.boundingRect(contour)
        if (
            x <= 1
            or y <= 1
            or x + box_width >= width - 1
            or y + box_height >= height - 1
        ):
            continue
        perimeter = float(cv2.arcLength(contour, True))
        polygon = cv2.approxPolyDP(contour, 0.01 * perimeter, True)
        if len(polygon) < 4:
            continue
        points = polygon.reshape(-1, 2)
        geometry = tuple((int(point[0]), int(point[1])) for point in points)
        bbox = (
            min(point[0] for point in geometry),
            min(point[1] for point in geometry),
            max(point[0] for point in geometry),
            max(point[1] for point in geometry),
        )
        candidates.append((bbox, polygon, area, perimeter))

    candidates.sort(key=lambda item: (item[0][1], item[0][0], item[0][3], item[0][2]))
    records = []
    for index, (_, polygon, area, perimeter) in enumerate(candidates, start=1):
        points = polygon.reshape(-1, 2)
        geometry = tuple(
            (float(point[0]), float(point[1]))
            for point in points
        )
        records.append(
            create_record(
                record_id=f"room-{index:04d}",
                element_class="room",
                geometry=geometry,
                confidence=None,
                detection_method=(
                    "Morphological closing and enclosed-region contour analysis"
                ),
                metadata=(
                    ("area_px2", round(area, 2)),
                    ("contour_perimeter_px", round(perimeter, 2)),
                    ("boundary_closing_kernel_px", closing_kernel_size),
                    ("coordinate_space", analysis.coordinate_space),
                ),
            )
        )
    return tuple(records)
