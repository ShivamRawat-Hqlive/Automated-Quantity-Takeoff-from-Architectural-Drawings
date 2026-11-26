import pytest
from PIL import Image

from boq.boq_generator import BoQItem
from boq.cost_estimator import CostBreakdown
from detection.detector import create_record
from measurement.quantity_calculator import (
    QuantityResult,
    QuantitySummary,
    RoomQuantity,
    WallQuantity,
)
from measurement.scale_calibration import calibrate_scale
from reports.report_data import build_report_snapshot
from verification.review_manager import ReviewManager


def make_snapshot():
    source = Image.new("RGB", (200, 160), "white")
    annotated = source.copy()
    annotated.putpixel((100, 80), (220, 60, 60))
    wall = create_record(
        record_id="wall-1",
        element_class="wall",
        geometry=((10, 10), (110, 10)),
        confidence=None,
        detection_method="test",
    )
    manager = ReviewManager((wall,), source_width=200, source_height=160)
    manager.set_status("wall-1", "verified")
    quantities = QuantityResult(
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
        rooms=(),
        summary=QuantitySummary(
            estimated_wall_length_m=0,
            verified_wall_length_m=1,
            manual_wall_length_m=0,
            unverified_wall_count=0,
            estimated_room_area_m2=0,
            verified_room_area_m2=0,
            manual_room_area_m2=0,
            floor_area_m2=0,
            manual_floor_area_m2=0,
            verified_door_count=0,
            verified_window_count=0,
            manual_door_count=0,
            manual_window_count=0,
            unverified_door_count=0,
            unverified_window_count=0,
        ),
    )
    boq = (
        BoQItem(
            item_id="wall-1",
            name="Wall",
            description="Verified wall",
            quantity=1,
            unit="m",
            rate=100,
            total=100,
            status="verified",
            rate_source="user-entered",
        ),
    )
    cost = CostBreakdown(
        subtotal=100,
        waste_amount=10,
        contingency_amount=11,
        tax_amount=21.78,
        grand_total=142.78,
        currency="INR",
        missing_rate_item_ids=(),
    )
    calibration = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=200,
        source_height=160,
        coordinate_frame="source image pixels; origin at top-left",
    )
    return build_report_snapshot(
        project_name="Test Project",
        filename="drawing.png",
        file_size_bytes=1234,
        source_image=source,
        annotated_image=annotated,
        quantities=quantities,
        review=manager.snapshot(),
        boq_items=boq,
        cost=cost,
        calibration=calibration,
        source_width=200,
        source_height=160,
        coordinate_frame="source image pixels; origin at top-left",
    )


def test_report_snapshot_contains_generation_metadata() -> None:
    snapshot = make_snapshot()

    assert snapshot.project_name == "Test Project"
    assert snapshot.generation_timestamp
    assert snapshot.currency == "INR"
    assert snapshot.calibration.calibrated is True
    assert snapshot.source_width == 200
    assert snapshot.source_height == 160
    assert snapshot.coordinate_frame == "source image pixels; origin at top-left"


def test_report_snapshot_copies_images_without_mutating_originals() -> None:
    snapshot = make_snapshot()
    source_copy = snapshot.source_image.copy()
    annotated_copy = snapshot.annotated_image.copy()

    snapshot.source_image.putpixel((0, 0), (1, 2, 3))
    snapshot.annotated_image.putpixel((0, 0), (4, 5, 6))

    assert snapshot.source_image.size == (200, 160)
    assert snapshot.annotated_image.size == (200, 160)
    assert source_copy.getpixel((0, 0)) == (255, 255, 255)
    assert annotated_copy.getpixel((0, 0)) == (255, 255, 255)


def test_missing_calibration_is_explicit() -> None:
    source = Image.new("RGB", (200, 160), "white")
    snapshot = make_snapshot()
    missing = build_report_snapshot(
        project_name=snapshot.project_name,
        filename=snapshot.filename,
        file_size_bytes=snapshot.file_size_bytes,
        source_image=source,
        annotated_image=source.copy(),
        quantities=snapshot.quantities,
        review=snapshot.review,
        boq_items=snapshot.boq_items,
        cost=snapshot.cost,
        calibration=None,
        source_width=200,
        source_height=160,
        coordinate_frame="source image pixels; origin at top-left",
    )

    assert missing.calibration.calibrated is False
    assert missing.calibration.pixels_per_metre is None


def test_snapshot_rejects_wrong_image_dimensions() -> None:
    snapshot = make_snapshot()
    with pytest.raises(ValueError, match="dimensions"):
        build_report_snapshot(
            project_name=snapshot.project_name,
            filename=snapshot.filename,
            file_size_bytes=snapshot.file_size_bytes,
            source_image=Image.new("RGB", (100, 100), "white"),
            annotated_image=snapshot.annotated_image,
            quantities=snapshot.quantities,
            review=snapshot.review,
            boq_items=snapshot.boq_items,
            cost=snapshot.cost,
            calibration=None,
            source_width=200,
            source_height=160,
            coordinate_frame="source image pixels; origin at top-left",
        )
