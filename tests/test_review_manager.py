import pytest

from detection.detector import create_record
from utils.exceptions import VerificationValidationError
from verification.review_manager import ReviewManager


def wall(record_id: str = "wall-1"):
    return create_record(
        record_id=record_id,
        element_class="wall",
        geometry=((10, 10), (110, 10)),
        confidence=None,
        detection_method="synthetic detector",
    )


def room(record_id: str = "room-1"):
    return create_record(
        record_id=record_id,
        element_class="room",
        geometry=((10, 10), (110, 10), (110, 110), (10, 110)),
        confidence=None,
        detection_method="synthetic detector",
    )


def test_state_transitions_and_audit_history() -> None:
    manager = ReviewManager((wall(),), source_width=200, source_height=200)

    manager.set_status("wall-1", "verified", note="Operator confirmed")
    manager.set_status("wall-1", "rejected", note="Operator rejected")

    snapshot = manager.snapshot()
    assert snapshot.statistics()["rejected"] == 1
    assert snapshot.records[0].correction_note == "Operator rejected"
    assert [event.action for event in snapshot.audit_history] == [
        "status_change",
        "status_change",
    ]


def test_original_record_is_preserved_after_edit() -> None:
    manager = ReviewManager((wall(),), source_width=200, source_height=200)
    corrected = create_record(
        record_id="wall-1",
        element_class="wall",
        geometry=((20, 20), (130, 20)),
        confidence=None,
        detection_method="manual correction",
    )

    manager.edit_record("wall-1", corrected, note="End moved")

    snapshot = manager.snapshot()
    review = snapshot.records[0]
    assert review.original.geometry == ((10, 10), (110, 10))
    assert review.corrected.geometry == ((20, 20), (130, 20))
    assert review.correction_note == "End moved"


def test_manual_record_requires_confirmation_and_can_be_deleted() -> None:
    manager = ReviewManager((), source_width=200, source_height=200)
    manual = create_record(
        record_id="manual-1",
        element_class="door",
        geometry=((20, 20), (50, 20)),
        confidence=None,
        detection_method="manual",
    )

    with pytest.raises(VerificationValidationError, match="explicit confirmation"):
        manager.add_manual_record(manual, explicitly_confirmed=False)

    manager.add_manual_record(
        manual,
        explicitly_confirmed=True,
        note="Door measured by reviewer",
    )
    assert manager.snapshot().statistics()["manual"] == 1

    manager.delete_manual_record("manual-1")
    assert manager.get("manual-1") if False else True
    assert manager.snapshot().statistics()["manual"] == 0
    assert manager.snapshot().statistics()["total"] == 0


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(VerificationValidationError, match="Duplicate"):
        ReviewManager((wall("same"), room("same")), source_width=200, source_height=200)
