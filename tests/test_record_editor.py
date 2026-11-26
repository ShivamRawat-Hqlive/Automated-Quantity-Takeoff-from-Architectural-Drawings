import pytest

from detection.detector import create_record
from utils.exceptions import VerificationValidationError
from verification.record_editor import (
    create_manual_record,
    edit_record,
    validate_record_geometry,
)


def test_wall_geometry_edit_returns_a_copy() -> None:
    original = create_record(
        record_id="wall-1",
        element_class="wall",
        geometry=((10, 10), (50, 10)),
        confidence=None,
        detection_method="detector",
    )

    corrected = edit_record(
        original,
        geometry=((15, 15), (75, 15)),
        source_width=100,
        source_height=100,
    )

    assert original.geometry == ((10, 10), (50, 10))
    assert corrected.geometry == ((15, 15), (75, 15))


def test_element_class_edit_is_validated() -> None:
    wall = create_record(
        record_id="element-1",
        element_class="wall",
        geometry=((10, 10), (50, 10)),
        confidence=None,
        detection_method="detector",
    )

    corrected = edit_record(
        wall,
        element_class="window",
        geometry=((10, 10), (50, 10)),
        source_width=100,
        source_height=100,
    )

    assert corrected.element_class == "window"


def test_invalid_coordinates_and_room_polygon_are_rejected() -> None:
    outside = create_record(
        record_id="wall-1",
        element_class="wall",
        geometry=((10, 10), (101, 10)),
        confidence=None,
        detection_method="detector",
    )
    incomplete_room = create_record(
        record_id="room-1",
        element_class="room",
        geometry=((10, 10), (20, 10)),
        confidence=None,
        detection_method="detector",
    )

    with pytest.raises(VerificationValidationError, match="outside"):
        validate_record_geometry(outside, source_width=100, source_height=100)
    with pytest.raises(VerificationValidationError, match="three points"):
        validate_record_geometry(incomplete_room, source_width=100, source_height=100)


def test_manual_record_is_unverified_until_confirmed() -> None:
    manual = create_manual_record(
        "manual-door",
        "door",
        ((10, 10), (40, 10)),
        source_width=100,
        source_height=100,
        note="Operator added",
    )

    assert manual.verification_status == "unverified"
    assert dict(manual.metadata)["manual_entry"] is True


def test_duplicate_manual_ids_are_checked_by_manager() -> None:
    from verification.review_manager import ReviewManager

    manager = ReviewManager((), source_width=100, source_height=100)
    manual = create_manual_record(
        "manual-1",
        "wall",
        ((10, 10), (40, 10)),
        source_width=100,
        source_height=100,
    )
    manager.add_manual_record(
        manual,
        explicitly_confirmed=True,
    )
    with pytest.raises(VerificationValidationError, match="Duplicate"):
        manager.add_manual_record(
            manual,
            explicitly_confirmed=True,
        )
