from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from detection.detector import create_record
from measurement.quantity_calculator import (
    QuantityResult,
    QuantitySummary,
    WallQuantity,
    RoomQuantity,
)
from measurement.scale_calibration import calibrate_scale
from visualization.annotation import (
    AnnotationOptions,
    create_annotated_drawing,
    export_annotated_png,
)


def make_wall(record_id: str = "wall-1"):
    return create_record(
        record_id=record_id,
        element_class="wall",
        geometry=((20, 30), (120, 30)),
        confidence=None,
        detection_method="synthetic wall",
    )


def make_room(record_id: str = "room-1"):
    return create_record(
        record_id=record_id,
        element_class="room",
        geometry=((20, 20), (100, 20), (100, 100), (20, 100)),
        confidence=None,
        detection_method="synthetic room",
    )


def make_door(record_id: str = "door-1"):
    return create_record(
        record_id=record_id,
        element_class="door",
        geometry=((120, 40), (150, 40)),
        confidence=None,
        detection_method="synthetic door",
    )


def make_window(record_id: str = "window-1"):
    return create_record(
        record_id=record_id,
        element_class="window",
        geometry=((40, 120), (80, 120)),
        confidence=None,
        detection_method="synthetic window",
    )


def make_quantity_result() -> QuantityResult:
    summary = QuantitySummary(
        estimated_wall_length_m=0,
        verified_wall_length_m=1,
        manual_wall_length_m=0,
        unverified_wall_count=0,
        estimated_room_area_m2=0,
        verified_room_area_m2=1,
        manual_room_area_m2=0,
        floor_area_m2=1,
        manual_floor_area_m2=0,
        verified_door_count=1,
        verified_window_count=1,
        manual_door_count=0,
        manual_window_count=0,
        unverified_door_count=0,
        unverified_window_count=0,
    )
    return QuantityResult(
        walls=(
            WallQuantity(
                id="wall-1",
                length_px=100,
                length_m=1,
                thickness_px=10,
                thickness_m=0.1,
                status="verified",
                quantity_type="verified",
            ),
        ),
        rooms=(
            RoomQuantity(
                id="room-1",
                area_px2=6400,
                area_m2=1,
                perimeter_px=320,
                perimeter_m=4,
                status="verified",
                quantity_type="verified",
            ),
        ),
        summary=summary,
    )


def test_wall_room_door_and_window_overlays_are_created() -> None:
    original = Image.new("RGB", (200, 160), "white")
    records = (make_wall(), make_room(), make_door(), make_window())

    result = create_annotated_drawing(
        original,
        records,
        quantity_result=make_quantity_result(),
        verified_ids=("wall-1", "room-1", "door-1", "window-1"),
    )

    assert result.width == 200
    assert result.height == 160
    assert result.image.mode == "RGB"
    assert result.summary.visible == 4
    assert result.summary.walls == 1
    assert result.summary.rooms == 1
    assert result.summary.doors == 1
    assert result.summary.windows == 1
    assert result.summary.verified == 4


def test_statuses_are_distinguished_and_rejected_is_not_verified() -> None:
    original = Image.new("RGB", (200, 160), "white")
    records = (
        make_wall("verified-wall"),
        make_room("unverified-room"),
        make_door("rejected-door"),
        make_window("manual-window"),
    )

    result = create_annotated_drawing(
        original,
        records,
        verified_ids=("verified-wall",),
        rejected_ids=("rejected-door",),
        manual_ids=("manual-window",),
    )

    assert result.summary.verified == 1
    assert result.summary.unverified == 1
    assert result.summary.rejected == 1
    assert result.summary.manual == 1


def test_visibility_filters_remove_categories_without_mutating_records() -> None:
    original = Image.new("RGB", (200, 160), "white")
    records = (make_wall(), make_room(), make_door(), make_window())
    original_copy = original.copy()

    result = create_annotated_drawing(
        original,
        records,
        options=AnnotationOptions(
            show_walls=False,
            show_rooms=True,
            show_doors=False,
            show_windows=True,
        ),
    )

    assert result.summary.visible == 2
    assert result.summary.walls == 0
    assert result.summary.rooms == 1
    assert result.summary.doors == 0
    assert result.summary.windows == 1
    assert np.array_equal(np.asarray(original), np.asarray(original_copy))


def test_missing_measurements_and_calibration_remain_honest() -> None:
    original = Image.new("RGB", (200, 160), "white")
    result = create_annotated_drawing(
        original,
        (make_wall(), make_room()),
        quantity_result=None,
        calibration=None,
        options=AnnotationOptions(show_ids=True, show_measurements=True),
    )

    assert result.summary.visible == 2


def test_mismatched_calibration_is_rejected() -> None:
    original = Image.new("RGB", (200, 160), "white")
    calibration = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=100,
        source_height=100,
        coordinate_frame="source image pixels; origin at top-left",
    )

    with pytest.raises(ValueError, match="does not match"):
        create_annotated_drawing(
            original,
            (make_wall(),),
            calibration=calibration,
        )


def test_out_of_raster_geometry_is_rejected() -> None:
    original = Image.new("RGB", (100, 100), "white")
    record = create_record(
        record_id="outside",
        element_class="wall",
        geometry=((10, 10), (120, 10)),
        confidence=None,
        detection_method="test",
    )

    with pytest.raises(ValueError, match="outside"):
        create_annotated_drawing(original, (record,))


def test_png_export_preserves_dimensions_and_is_decodable() -> None:
    original = Image.new("RGB", (200, 160), "white")
    annotation = create_annotated_drawing(
        original,
        (make_room(),),
    )

    png_bytes = export_annotated_png(annotation)
    exported = Image.open(BytesIO(png_bytes))

    assert exported.format == "PNG"
    assert exported.size == (200, 160)
    assert exported.mode == "RGB"


def test_annotation_does_not_modify_or_resize_original() -> None:
    original = Image.new("RGB", (200, 160), "white")
    original_pixels = np.asarray(original).copy()

    create_annotated_drawing(
        original,
        (make_wall(), make_room(), make_door(), make_window()),
    )

    assert original.size == (200, 160)
    assert np.array_equal(np.asarray(original), original_pixels)
