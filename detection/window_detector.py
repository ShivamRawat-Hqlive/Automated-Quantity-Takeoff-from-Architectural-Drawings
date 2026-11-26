"""Conservative window candidates from wall gaps and bounded frame patterns."""

from detection.detector import DetectionRecord, create_record
from detection.wall_detector import WallOpening, find_wall_openings
from processing.image_preprocessor import ImageAnalysis, LineCandidate


def _line_parts(line: LineCandidate) -> tuple[str, float, int, int]:
    if line.orientation == "horizontal":
        return (
            "horizontal",
            (line.start[1] + line.end[1]) / 2,
            min(line.start[0], line.end[0]),
            max(line.start[0], line.end[0]),
        )
    return (
        "vertical",
        (line.start[0] + line.end[0]) / 2,
        min(line.start[1], line.end[1]),
        max(line.start[1], line.end[1]),
    )


def _bounded_frame_lines(
    analysis: ImageAnalysis,
    opening: WallOpening,
    *,
    axis_tolerance: int = 18,
    endpoint_tolerance: int = 8,
) -> tuple[float, ...]:
    opening_low = min(
        opening.start[0] if opening.orientation == "horizontal" else opening.start[1],
        opening.end[0] if opening.orientation == "horizontal" else opening.end[1],
    )
    opening_high = max(
        opening.start[0] if opening.orientation == "horizontal" else opening.start[1],
        opening.end[0] if opening.orientation == "horizontal" else opening.end[1],
    )
    frame_axes = []
    for line in analysis.horizontal_lines + analysis.vertical_lines:
        orientation, axis, low, high = _line_parts(line)
        if orientation != opening.orientation:
            continue
        axis_spacing = abs(axis - opening.axis)
        if not 2 <= axis_spacing <= axis_tolerance:
            continue
        if abs(low - opening_low) > endpoint_tolerance:
            continue
        if abs(high - opening_high) > endpoint_tolerance:
            continue
        frame_axes.append(axis)

    return tuple(sorted(frame_axes))


def _has_window_frame(analysis: ImageAnalysis, opening: WallOpening) -> bool:
    axes = _bounded_frame_lines(analysis, opening)
    unique_axes: list[float] = []
    for axis in axes:
        if not unique_axes or abs(axis - unique_axes[-1]) > 2:
            unique_axes.append(axis)
    return any(
        2 <= unique_axes[index + 1] - unique_axes[index] <= 18
        for index in range(len(unique_axes) - 1)
    )


def detect_windows(analysis: ImageAnalysis) -> tuple[DetectionRecord, ...]:
    """Require a paired wall gap and two bounded, parallel frame-line candidates."""
    records = []
    for opening in find_wall_openings(analysis):
        if not _has_window_frame(analysis, opening):
            continue
        index = len(records) + 1
        records.append(
            create_record(
                record_id=f"window-{index:04d}",
                element_class="window",
                geometry=(
                    (float(opening.start[0]), float(opening.start[1])),
                    (float(opening.end[0]), float(opening.end[1])),
                ),
                confidence=None,
                detection_method=(
                    "Paired wall gap and two bounded parallel frame-line rule"
                ),
                metadata=(
                    ("wall_orientation", opening.orientation),
                    ("opening_width_px", opening.gap_px),
                    ("frame_line_candidates", len(_bounded_frame_lines(analysis, opening))),
                ),
            )
        )
    return tuple(records)
