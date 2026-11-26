"""Quantity summaries that preserve estimated, manual, verified and unverified states."""

from dataclasses import dataclass

from detection.detector import DetectionRecord
from measurement.geometry import (
    deduplicate_geometry,
    filter_valid_room_records,
    pixel_area_to_square_metre,
    pixel_length_to_metre,
    polygon_area_px2,
    polygon_perimeter_px,
)
from measurement.scale_calibration import ScaleCalibration
from utils.exceptions import MeasurementValidationError


@dataclass(frozen=True)
class WallQuantity:
    id: str
    length_px: float
    length_m: float | None
    thickness_px: int | None
    thickness_m: float | None
    status: str
    quantity_type: str


@dataclass(frozen=True)
class RoomQuantity:
    id: str
    area_px2: float
    area_m2: float | None
    perimeter_px: float
    perimeter_m: float | None
    status: str
    quantity_type: str


@dataclass(frozen=True)
class QuantitySummary:
    estimated_wall_length_m: float
    verified_wall_length_m: float
    manual_wall_length_m: float
    unverified_wall_count: int
    estimated_room_area_m2: float
    verified_room_area_m2: float
    manual_room_area_m2: float
    floor_area_m2: float
    manual_floor_area_m2: float
    verified_door_count: int
    verified_window_count: int
    manual_door_count: int
    manual_window_count: int
    unverified_door_count: int
    unverified_window_count: int


@dataclass(frozen=True)
class QuantityResult:
    walls: tuple[WallQuantity, ...]
    rooms: tuple[RoomQuantity, ...]
    summary: QuantitySummary


def calculate_quantities(
    records: tuple[DetectionRecord, ...],
    calibration: ScaleCalibration | None,
    *,
    manual_wall_length_m: float = 0,
    manual_room_area_m2: float = 0,
    manual_door_count: int = 0,
    manual_window_count: int = 0,
    verified_record_ids: tuple[str, ...] = (),
) -> QuantityResult:
    """Calculate quantities without promoting candidates or fabricating results."""
    for value in (manual_wall_length_m, manual_room_area_m2):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
        ):
            raise MeasurementValidationError(
                "Manual wall and room quantities must be non-negative numbers."
            )
    for value in (manual_door_count, manual_window_count):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise MeasurementValidationError(
                "Manual element counts must be non-negative integers."
            )
    verified_ids = set(verified_record_ids)
    deduplicated_walls = deduplicate_geometry(
        tuple(record for record in records if record.element_class == "wall")
    )
    room_records = filter_valid_room_records(records)
    deduplicated = deduplicated_walls + room_records + tuple(
        record
        for record in deduplicate_geometry(records)
        if record.element_class not in {"wall", "room"}
    )
    wall_quantities: list[WallQuantity] = []
    room_quantities: list[RoomQuantity] = []

    for record in deduplicated:
        if record.element_class == "wall" and len(record.geometry) == 2:
            from measurement.geometry import line_length_px

            length_px = line_length_px(record.geometry[0], record.geometry[1])
            thickness_px = None
            for key, value in record.metadata:
                if key == "estimated_thickness_px" and isinstance(value, int):
                    thickness_px = value
            status = "verified" if record.id in verified_ids else "unverified"
            wall_quantities.append(
                WallQuantity(
                    id=record.id,
                    length_px=length_px,
                    length_m=(
                        pixel_length_to_metre(length_px, calibration)
                        if calibration is not None
                        else None
                    ),
                    thickness_px=thickness_px,
                    thickness_m=(
                        pixel_length_to_metre(float(thickness_px), calibration)
                        if calibration is not None and thickness_px is not None
                        else None
                    ),
                    status=status,
                    quantity_type="estimated" if status == "unverified" else "verified",
                )
            )

        elif record.element_class == "room" and len(record.geometry) >= 3:
            try:
                area_px2 = polygon_area_px2(record.geometry)
                perimeter_px = polygon_perimeter_px(record.geometry)
            except MeasurementValidationError:
                continue
            status = "verified" if record.id in verified_ids else "unverified"
            room_quantities.append(
                RoomQuantity(
                    id=record.id,
                    area_px2=area_px2,
                    area_m2=(
                        pixel_area_to_square_metre(area_px2, calibration)
                        if calibration is not None
                        else None
                    ),
                    perimeter_px=perimeter_px,
                    perimeter_m=(
                        pixel_length_to_metre(perimeter_px, calibration)
                        if calibration is not None
                        else None
                    ),
                    status=status,
                    quantity_type="estimated" if status == "unverified" else "verified",
                )
            )

    unverified_walls = [
        wall for wall in wall_quantities if wall.status == "unverified"
    ]
    verified_walls = [
        wall for wall in wall_quantities if wall.status == "verified"
    ]
    unverified_rooms = [
        room for room in room_quantities if room.status == "unverified"
    ]
    verified_rooms = [
        room for room in room_quantities if room.status == "verified"
    ]

    estimated_wall_length = sum(
        wall.length_m or 0 for wall in unverified_walls
    )
    verified_wall_length = sum(
        wall.length_m or 0 for wall in verified_walls
    )
    estimated_room_area = sum(
        room.area_m2 or 0 for room in unverified_rooms
    )
    verified_room_area = sum(
        room.area_m2 or 0 for room in verified_rooms
    )
    unverified_doors = sum(
        1
        for record in deduplicated
        if record.element_class == "door"
        and record.id not in verified_ids
    )
    unverified_windows = sum(
        1
        for record in deduplicated
        if record.element_class == "window"
        and record.id not in verified_ids
    )
    verified_doors = sum(
        1
        for record in deduplicated
        if record.element_class == "door"
        and record.id in verified_ids
    )
    verified_windows = sum(
        1
        for record in deduplicated
        if record.element_class == "window"
        and record.id in verified_ids
    )

    summary = QuantitySummary(
        estimated_wall_length_m=estimated_wall_length,
        verified_wall_length_m=verified_wall_length,
        manual_wall_length_m=manual_wall_length_m,
        unverified_wall_count=len(unverified_walls),
        estimated_room_area_m2=estimated_room_area,
        verified_room_area_m2=verified_room_area,
        manual_room_area_m2=manual_room_area_m2,
        floor_area_m2=(
            verified_room_area
            if verified_rooms
            else 0
        ),
        manual_floor_area_m2=manual_room_area_m2,
        verified_door_count=verified_doors,
        verified_window_count=verified_windows,
        manual_door_count=manual_door_count,
        manual_window_count=manual_window_count,
        unverified_door_count=unverified_doors,
        unverified_window_count=unverified_windows,
    )
    return QuantityResult(
        walls=tuple(wall_quantities),
        rooms=tuple(room_quantities),
        summary=summary,
    )
