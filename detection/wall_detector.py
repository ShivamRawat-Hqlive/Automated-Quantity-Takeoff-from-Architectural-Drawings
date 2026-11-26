"""Merge Hough line candidates into unverified wall candidates."""

from dataclasses import dataclass

from processing.image_preprocessor import ImageAnalysis, LineCandidate
from detection.detector import DetectionRecord, create_record


@dataclass(frozen=True)
class WallSegment:
    """Merged collinear segment in source-image pixel coordinates."""

    orientation: str
    start: tuple[int, int]
    end: tuple[int, int]
    support_count: int

    @property
    def axis(self) -> float:
        if self.orientation == "horizontal":
            return (self.start[1] + self.end[1]) / 2
        return (self.start[0] + self.end[0]) / 2

    @property
    def interval(self) -> tuple[int, int]:
        if self.orientation == "horizontal":
            return min(self.start[0], self.end[0]), max(self.start[0], self.end[0])
        return min(self.start[1], self.end[1]), max(self.start[1], self.end[1])

    @property
    def length(self) -> int:
        low, high = self.interval
        return high - low


@dataclass(frozen=True)
class WallOpening:
    """A collinear gap between wall-line candidates, not a classified element."""

    orientation: str
    start: tuple[int, int]
    end: tuple[int, int]
    gap_px: int

    @property
    def axis(self) -> float:
        if self.orientation == "horizontal":
            return (self.start[1] + self.end[1]) / 2
        return (self.start[0] + self.end[0]) / 2


@dataclass
class _SegmentGroup:
    orientation: str
    axis: float
    low: int
    high: int
    support_count: int


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


def merge_wall_segments(
    analysis: ImageAnalysis,
    *,
    axis_tolerance: int = 4,
    merge_gap: int = 8,
) -> tuple[WallSegment, ...]:
    """Merge overlapping, duplicate, or closely separated collinear Hough lines."""
    lines = analysis.horizontal_lines + analysis.vertical_lines
    normalized = sorted(
        (_line_parts(line) for line in lines),
        key=lambda item: (item[0], item[1], item[2], item[3]),
    )
    groups: list[_SegmentGroup] = []

    for orientation, axis, low, high in normalized:
        compatible = [
            group
            for group in groups
            if group.orientation == orientation
            and abs(group.axis - axis) <= axis_tolerance
            and low <= group.high + merge_gap
            and high >= group.low - merge_gap
        ]
        if not compatible:
            groups.append(_SegmentGroup(orientation, axis, low, high, 1))
            continue

        group = min(compatible, key=lambda item: abs(item.axis - axis))
        group.axis = (
            group.axis * group.support_count + axis
        ) / (group.support_count + 1)
        group.low = min(group.low, low)
        group.high = max(group.high, high)
        group.support_count += 1

    merged = []
    for group in groups:
        axis = round(group.axis)
        if group.orientation == "horizontal":
            start = (group.low, axis)
            end = (group.high, axis)
        else:
            start = (axis, group.low)
            end = (axis, group.high)
        merged.append(
            WallSegment(
                orientation=group.orientation,
                start=start,
                end=end,
                support_count=group.support_count,
            )
        )
    return tuple(
        sorted(
            merged,
            key=lambda segment: (
                segment.orientation,
                segment.start[1],
                segment.start[0],
                segment.end[1],
                segment.end[0],
            ),
        )
    )


def _estimate_thickness(
    segment: WallSegment,
    segments: tuple[WallSegment, ...],
    *,
    max_spacing: int = 32,
) -> int | None:
    low, high = segment.interval
    possible: list[tuple[int, float]] = []
    for other in segments:
        if other is segment or other.orientation != segment.orientation:
            continue
        spacing = round(abs(segment.axis - other.axis))
        if not 2 <= spacing <= max_spacing:
            continue
        other_low, other_high = other.interval
        overlap = min(high, other_high) - max(low, other_low)
        shorter_length = min(segment.length, other.length)
        longer_length = max(segment.length, other.length)
        if shorter_length <= 0 or overlap / shorter_length < 0.8:
            continue
        if shorter_length / longer_length < 0.8:
            continue
        possible.append((spacing, overlap / shorter_length))

    possible.sort(key=lambda pair: pair[0])
    if not possible:
        return None
    if len(possible) > 1 and possible[1][0] <= possible[0][0] * 1.25:
        return None
    return possible[0][0]


def detect_walls(analysis: ImageAnalysis) -> tuple[DetectionRecord, ...]:
    """Produce merged horizontal/vertical wall-line candidates, not verified walls."""
    segments = merge_wall_segments(analysis)
    records = []
    for index, segment in enumerate(segments, start=1):
        thickness = _estimate_thickness(segment, segments)
        metadata = (
            ("orientation", segment.orientation),
            ("supporting_hough_segments", segment.support_count),
            ("estimated_thickness_px", thickness),
            (
                "thickness_estimate_basis",
                "spacing between similar parallel candidates" if thickness else None,
            ),
        )
        records.append(
            create_record(
                record_id=f"wall-{index:04d}",
                element_class="wall",
                geometry=(
                    (float(segment.start[0]), float(segment.start[1])),
                    (float(segment.end[0]), float(segment.end[1])),
                ),
                confidence=None,
                detection_method=(
                    "Hough line candidates merged by orientation, "
                    "axis proximity, and segment overlap"
                ),
                metadata=metadata,
            )
        )
    return tuple(records)


def find_wall_openings(
    analysis: ImageAnalysis,
    *,
    min_gap: int = 16,
    max_gap: int = 120,
    axis_tolerance: int = 3,
) -> tuple[WallOpening, ...]:
    """Find measurable line gaps only; callers must apply symbol-specific rules."""
    segments = merge_wall_segments(analysis)
    openings: list[WallOpening] = []
    for first_index, first in enumerate(segments):
        first_low, first_high = first.interval
        for second in segments[first_index + 1 :]:
            if second.orientation != first.orientation:
                continue
            if abs(second.axis - first.axis) > axis_tolerance:
                continue
            second_low, second_high = second.interval
            if second_low < first_low:
                continue
            gap = second_low - first_high
            if not min_gap <= gap <= max_gap:
                continue
            axis = round((first.axis + second.axis) / 2)
            if first.orientation == "horizontal":
                start = (first_high, axis)
                end = (second_low, axis)
            else:
                start = (axis, first_high)
                end = (axis, second_low)
            openings.append(
                WallOpening(
                    orientation=first.orientation,
                    start=start,
                    end=end,
                    gap_px=gap,
                )
            )
            break
    return tuple(openings)
