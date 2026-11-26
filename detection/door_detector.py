"""Conservative door-symbol candidates requiring a wall gap and swing evidence."""

import math

import numpy as np

from detection.detector import DetectionRecord, create_record
from detection.wall_detector import WallOpening, find_wall_openings
from processing.image_preprocessor import ImageAnalysis, LineCandidate


def _perpendicular_leaf_near_hinge(
    analysis: ImageAnalysis,
    opening: WallOpening,
    hinge: tuple[int, int],
) -> bool:
    candidates = analysis.horizontal_lines + analysis.vertical_lines
    expected_orientation = (
        "vertical" if opening.orientation == "horizontal" else "horizontal"
    )
    for line in candidates:
        if line.orientation != expected_orientation:
            continue
        length = math.hypot(
            line.end[0] - line.start[0],
            line.end[1] - line.start[1],
        )
        if not opening.gap_px * 0.65 <= length <= opening.gap_px * 1.35:
            continue
        if min(
            math.dist(line.start, hinge),
            math.dist(line.end, hinge),
        ) <= max(8, opening.gap_px * 0.15):
            return True
    return False


def _arc_in_hinge_quadrant(
    angles: np.ndarray,
    orientation: str,
    at_start: bool,
) -> np.ndarray:
    if orientation == "horizontal" and at_start:
        selected = (angles <= 90) | (angles >= 270)
        return np.where(angles[selected] > 180, angles[selected] - 360, angles[selected])
    if orientation == "horizontal":
        selected = (angles >= 90) & (angles <= 270)
        return angles[selected] - 180
    if at_start:
        selected = angles <= 180
        return angles[selected] - 90
    selected = angles >= 180
    return angles[selected] - 270


def _has_swing_arc(
    analysis: ImageAnalysis,
    opening: WallOpening,
    hinge: tuple[int, int],
) -> bool:
    radius = float(opening.gap_px)
    tolerance = max(3.0, radius * 0.15)
    at_start = hinge == opening.start

    for contour in analysis.contours:
        points = np.asarray(contour, dtype=np.float32)
        if len(points) < 8:
            continue
        offsets = points - np.asarray(hinge, dtype=np.float32)
        distances = np.hypot(offsets[:, 0], offsets[:, 1])
        on_arc = np.abs(distances - radius) <= tolerance
        angles = np.degrees(np.arctan2(offsets[:, 1], offsets[:, 0])) % 360
        selected_angles = _arc_in_hinge_quadrant(
            angles[on_arc],
            opening.orientation,
            at_start,
        )
        if len(selected_angles) < 8:
            continue
        angular_bins = np.unique(np.round(selected_angles / 5))
        angular_span = float(selected_angles.max() - selected_angles.min())
        if len(angular_bins) >= 6 and 35 <= angular_span <= 125:
            return True
    return False


def _door_symbol_hinge(
    analysis: ImageAnalysis,
    opening: WallOpening,
) -> tuple[int, int] | None:
    for hinge in (opening.start, opening.end):
        if _perpendicular_leaf_near_hinge(analysis, opening, hinge) and _has_swing_arc(
            analysis,
            opening,
            hinge,
        ):
            return hinge
    return None


def detect_doors(analysis: ImageAnalysis) -> tuple[DetectionRecord, ...]:
    """Return door candidates only when a wall gap, leaf, and swing arc agree."""
    records = []
    for opening in find_wall_openings(analysis):
        hinge = _door_symbol_hinge(analysis, opening)
        if hinge is None:
            continue
        index = len(records) + 1
        records.append(
            create_record(
                record_id=f"door-{index:04d}",
                element_class="door",
                geometry=(
                    (float(opening.start[0]), float(opening.start[1])),
                    (float(opening.end[0]), float(opening.end[1])),
                ),
                confidence=None,
                detection_method=(
                    "Paired wall gap, perpendicular leaf, and swing-arc contour rule"
                ),
                metadata=(
                    ("wall_orientation", opening.orientation),
                    ("opening_width_px", opening.gap_px),
                    ("hinge_x_px", hinge[0]),
                    ("hinge_y_px", hinge[1]),
                    ("swing_arc_found", True),
                    ("leaf_found", True),
                ),
            )
        )
    return tuple(records)
