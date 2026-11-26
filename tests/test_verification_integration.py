import json

import pytest

from detection.detector import create_record
from measurement.quantity_calculator import calculate_quantities
from measurement.scale_calibration import calibrate_scale
from verification.review_manager import ReviewManager
from verification.record_editor import edit_record


def wall(record_id: str = "wall-1", geometry=None):
    return create_record(
        record_id=record_id,
        element_class="wall",
        geometry=geometry or ((0, 0), (100, 0)),
        confidence=None,
        detection_method="synthetic",
    )


def test_quantity_recalculation_excludes_rejected_and_unverified() -> None:
    manager = ReviewManager(
        (
            wall("wall-verified", ((0, 0), (100, 0))),
            wall("wall-rejected", ((0, 20), (100, 20))),
            wall("wall-unverified", ((0, 40), (100, 40))),
        ),
        source_width=200,
        source_height=200,
    )
    manager.set_status("wall-verified", "verified")
    manager.set_status("wall-rejected", "rejected")

    calibrated = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=200,
        source_height=200,
        coordinate_frame="source image pixels; origin at top-left",
    )
    quantities = manager.snapshot().recalculated_quantities(calibrated)

    assert quantities.summary.verified_wall_length_m == 1
    assert quantities.summary.unverified_wall_count == 1
    assert len([wall for wall in quantities.walls if wall.status == "verified"]) == 1


def test_geometry_change_changes_recalculated_quantity() -> None:
    original = wall("wall-1")
    manager = ReviewManager((original,), source_width=200, source_height=200)
    corrected = edit_record(
        original,
        geometry=((0, 0), (200, 0)),
        source_width=200,
        source_height=200,
    )
    manager.edit_record("wall-1", corrected)
    manager.set_status("wall-1", "verified")

    calibrated = calibrate_scale(
        0,
        0,
        100,
        0,
        1,
        "m",
        source_width=200,
        source_height=200,
        coordinate_frame="source image pixels; origin at top-left",
    )
    quantities = manager.snapshot().recalculated_quantities(calibrated)

    assert quantities.summary.verified_wall_length_m == 2


def test_filtering_and_statistics() -> None:
    manager = ReviewManager(
        (wall("wall-1"), wall("wall-2")),
        source_width=200,
        source_height=200,
    )
    manager.set_status("wall-1", "verified")

    snapshot = manager.snapshot()
    assert snapshot.statistics()["verified"] == 1
    assert snapshot.statistics()["unverified"] == 1
    assert len(snapshot.filter_records(search="wall")) == 2
    assert len(snapshot.filter_records(status="verified", element_class="wall")) == 1


def test_json_export_import_and_original_preservation() -> None:
    original = wall("wall-1")
    manager = ReviewManager((original,), source_width=200, source_height=200)
    corrected = edit_record(
        original,
        geometry=((0, 0), (150, 0)),
        source_width=200,
        source_height=200,
    )
    manager.edit_record("wall-1", corrected, note="Exported correction")
    manager.set_status("wall-1", "verified", note="Confirmed")

    text = manager.snapshot().to_json()
    payload = json.loads(text)
    assert payload["source_width"] == 200
    assert payload["records"][0]["original"]["geometry"] == [[0.0, 0.0], [100.0, 0.0]]

    restored = __import__(
        "verification.review_manager",
        fromlist=["ReviewManager"],
    ).ReviewManager.from_json(text)
    snapshot = restored.snapshot()
    assert snapshot.records[0].corrected.geometry == ((0.0, 0.0), (150.0, 0.0))
    assert snapshot.records[0].status == "verified"


def test_invalid_import_is_rejected() -> None:
    from verification.review_manager import ReviewManager

    with pytest.raises(Exception):
        ReviewManager.from_json("{not-json")
