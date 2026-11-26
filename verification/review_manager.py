"""Human review state, audit history, persistence, and quantity integration."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Literal

from detection.detector import DetectionRecord
from measurement.quantity_calculator import QuantityResult, calculate_quantities
from measurement.scale_calibration import ScaleCalibration
from utils.exceptions import VerificationValidationError
from verification.record_editor import validate_record_geometry

ReviewStatus = Literal["unverified", "verified", "rejected", "manual"]


@dataclass(frozen=True)
class ReviewAuditEvent:
    """One immutable correction or status transition."""

    record_id: str
    action: str
    before_status: str
    after_status: str
    note: str
    timestamp: str


@dataclass(frozen=True)
class ReviewRecord:
    """A corrected record plus active review status and audit count."""

    original: DetectionRecord
    corrected: DetectionRecord
    status: ReviewStatus
    source: Literal["detector", "manual"]
    correction_note: str


@dataclass(frozen=True)
class ReviewSnapshot:
    """Searchable review state and derived verified records."""

    source_width: int
    source_height: int
    records: tuple[ReviewRecord, ...]
    audit_history: tuple[ReviewAuditEvent, ...]

    def by_status(self, status: ReviewStatus) -> tuple[ReviewRecord, ...]:
        return tuple(record for record in self.records if record.status == status)

    def filter_records(
        self,
        *,
        search: str = "",
        status: ReviewStatus | str = "all",
        element_class: str = "all",
    ) -> tuple[ReviewRecord, ...]:
        search_text = search.strip().lower()
        filtered = []
        for record in self.records:
            if status != "all" and record.status != status:
                continue
            if element_class != "all" and record.corrected.element_class != element_class:
                continue
            searchable = " ".join(
                (
                    record.corrected.id,
                    record.corrected.element_class,
                    record.correction_note,
                    record.original.detection_method,
                )
            ).lower()
            if search_text and search_text not in searchable:
                continue
            filtered.append(record)
        return tuple(filtered)

    def statistics(self) -> dict[str, int]:
        return {
            "unverified": len(self.by_status("unverified")),
            "verified": len(self.by_status("verified")),
            "rejected": len(self.by_status("rejected")),
            "manual": len(self.by_status("manual")),
            "total": len(self.records),
        }

    def corrected_records(self) -> tuple[DetectionRecord, ...]:
        prioritized = sorted(
            (
                record
                for record in self.records
                if record.status != "rejected"
            ),
            key=lambda record: (
                0 if record.status in {"verified", "manual"} else 1,
                record.corrected.id,
            ),
        )
        return tuple(record.corrected for record in prioritized)

    def verified_record_ids(self) -> tuple[str, ...]:
        return tuple(
            record.corrected.id
            for record in self.records
            if record.status in {"verified", "manual"}
        )

    def recalculated_quantities(
        self,
        calibration: ScaleCalibration | None,
    ) -> QuantityResult:
        return calculate_quantities(
            self.corrected_records(),
            calibration,
            verified_record_ids=self.verified_record_ids(),
        )

    def to_json(self) -> str:
        """Export active review state and audit history as JSON."""
        payload = {
            "source_width": self.source_width,
            "source_height": self.source_height,
            "records": [
                {
                    "original": _record_to_dict(record.original),
                    "corrected": _record_to_dict(record.corrected),
                    "status": record.status,
                    "source": record.source,
                    "correction_note": record.correction_note,
                }
                for record in self.records
            ],
            "audit_history": [
                {
                    "record_id": event.record_id,
                    "action": event.action,
                    "before_status": event.before_status,
                    "after_status": event.after_status,
                    "note": event.note,
                    "timestamp": event.timestamp,
                }
                for event in self.audit_history
            ],
        }
        return json.dumps(payload, indent=2)


class ReviewManager:
    """Stateful in-memory review workflow."""

    def __init__(
        self,
        original_records: tuple[DetectionRecord, ...],
        *,
        source_width: int,
        source_height: int,
    ) -> None:
        if source_width <= 0 or source_height <= 0:
            raise VerificationValidationError("Source raster dimensions must be positive.")
        self.source_width = source_width
        self.source_height = source_height
        self.original_records = tuple(original_records)
        self._records: dict[str, ReviewRecord] = {}
        self._audit_history: list[ReviewAuditEvent] = []
        for record in original_records:
            self._validate_id(record.id)
            self._records[record.id] = ReviewRecord(
                original=record,
                corrected=record,
                status="unverified",
                source="detector",
                correction_note="",
            )

    def snapshot(self) -> ReviewSnapshot:
        return ReviewSnapshot(
            source_width=self.source_width,
            source_height=self.source_height,
            records=tuple(
                sorted(
                    self._records.values(),
                    key=lambda record: record.corrected.id,
                )
            ),
            audit_history=tuple(self._audit_history),
        )

    def get(self, record_id: str) -> ReviewRecord:
        if record_id not in self._records:
            raise VerificationValidationError(f"Unknown review record ID: {record_id}")
        return self._records[record_id]

    def _validate_id(self, record_id: str) -> None:
        if not record_id or not record_id.strip():
            raise VerificationValidationError("Record ID is required.")
        if record_id in self._records:
            raise VerificationValidationError(
                f"Duplicate record ID: {record_id}"
            )

    def set_status(
        self,
        record_id: str,
        status: ReviewStatus,
        *,
        note: str = "",
    ) -> ReviewRecord:
        if status not in {"unverified", "verified", "rejected", "manual"}:
            raise VerificationValidationError("Unsupported review status.")
        current = self.get(record_id)
        updated = ReviewRecord(
            original=current.original,
            corrected=current.corrected,
            status=status,
            source="manual" if status == "manual" or current.source == "manual" else "detector",
            correction_note=note.strip() or current.correction_note,
        )
        self._records[record_id] = updated
        self._audit(
            record_id,
            action="status_change",
            before_status=current.status,
            after_status=status,
            note=updated.correction_note,
        )
        return updated

    def edit_record(
        self,
        record_id: str,
        corrected: DetectionRecord,
        *,
        note: str = "",
    ) -> ReviewRecord:
        current = self.get(record_id)
        if corrected.id != record_id:
            raise VerificationValidationError(
                "Corrected record ID must match the original record ID."
            )
        if corrected.id in self._records and self._records[corrected.id] is not current:
            raise VerificationValidationError(f"Duplicate record ID: {corrected.id}")
        updated = ReviewRecord(
            original=current.original,
            corrected=corrected,
            status=current.status,
            source=current.source,
            correction_note=note.strip() or current.correction_note,
        )
        self._records[record_id] = updated
        self._audit(
            record_id,
            action="geometry_edit",
            before_status=current.status,
            after_status=current.status,
            note=updated.correction_note,
        )
        return updated

    def add_manual_record(
        self,
        record: DetectionRecord,
        *,
        note: str = "",
        explicitly_confirmed: bool,
    ) -> ReviewRecord:
        if not explicitly_confirmed:
            raise VerificationValidationError(
                "Manual records require explicit confirmation."
            )
        self._validate_id(record.id)
        updated = ReviewRecord(
            original=record,
            corrected=record,
            status="manual",
            source="manual",
            correction_note=note.strip(),
        )
        self._records[record.id] = updated
        self._audit(
            record.id,
            action="manual_add",
            before_status="unverified",
            after_status="manual",
            note=note.strip(),
        )
        return updated

    def delete_manual_record(self, record_id: str) -> None:
        current = self.get(record_id)
        if current.source != "manual":
            raise VerificationValidationError(
                "Only manually added records can be deleted."
            )
        del self._records[record_id]
        self._audit(
            record_id,
            action="manual_delete",
            before_status=current.status,
            after_status="rejected",
            note="Manually added record deleted.",
        )

    def _audit(
        self,
        record_id: str,
        *,
        action: str,
        before_status: str,
        after_status: str,
        note: str,
    ) -> None:
        self._audit_history.append(
            ReviewAuditEvent(
                record_id=record_id,
                action=action,
                before_status=before_status,
                after_status=after_status,
                note=note,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )

    @classmethod
    def from_json(cls, text: str) -> "ReviewManager":
        try:
            payload = json.loads(text)
            source_width = int(payload["source_width"])
            source_height = int(payload["source_height"])
            records = payload["records"]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise VerificationValidationError("Invalid review JSON.") from exc

        originals: list[DetectionRecord] = []
        restored: list[ReviewRecord] = []
        for row in records:
            try:
                original = _record_from_dict(row["original"])
                corrected = _record_from_dict(row["corrected"])
                status = row["status"]
                source = row["source"]
                note = row["correction_note"]
            except (KeyError, TypeError, ValueError) as exc:
                raise VerificationValidationError(
                    "Review JSON contains an invalid record."
                ) from exc
            if status not in {"unverified", "verified", "rejected", "manual"}:
                raise VerificationValidationError("Review JSON has invalid status.")
            if source not in {"detector", "manual"}:
                raise VerificationValidationError("Review JSON has invalid source.")
            corrected = validate_record_geometry(
                corrected,
                source_width=source_width,
                source_height=source_height,
            )
            original = validate_record_geometry(
                original,
                source_width=source_width,
                source_height=source_height,
            )
            if source == "detector":
                originals.append(original)
            restored.append(
                ReviewRecord(
                    original=original,
                    corrected=corrected,
                    status=status,
                    source=source,
                    correction_note=str(note),
                )
            )

        manager = cls(
            tuple(originals),
            source_width=source_width,
            source_height=source_height,
        )
        manager._records = {
            record.corrected.id: record
            for record in restored
        }
        if len(manager._records) != len(restored):
            raise VerificationValidationError("Review JSON contains duplicate record IDs.")

        audit_rows = payload.get("audit_history", [])
        for row in audit_rows:
            try:
                manager._audit_history.append(
                    ReviewAuditEvent(
                        record_id=row["record_id"],
                        action=row["action"],
                        before_status=row["before_status"],
                        after_status=row["after_status"],
                        note=row["note"],
                        timestamp=row["timestamp"],
                    )
                )
            except (KeyError, TypeError) as exc:
                raise VerificationValidationError(
                    "Review JSON contains invalid audit history."
                ) from exc
        return manager


def _record_to_dict(record: DetectionRecord) -> dict:
    return {
        "id": record.id,
        "element_class": record.element_class,
        "geometry": [list(point) for point in record.geometry],
        "bbox": list(record.bbox),
        "confidence": record.confidence,
        "detection_method": record.detection_method,
        "verification_status": record.verification_status,
        "metadata": [
            [key, value]
            for key, value in record.metadata
        ],
    }


def _record_from_dict(payload: dict) -> DetectionRecord:
    geometry = tuple(
        (float(point[0]), float(point[1]))
        for point in payload["geometry"]
    )
    bbox = tuple(float(value) for value in payload["bbox"])
    if len(bbox) != 4:
        raise VerificationValidationError("Invalid record bounding box.")
    element_class = payload["element_class"]
    if element_class not in {"wall", "room", "door", "window"}:
        raise VerificationValidationError("Invalid record element class.")
    metadata = tuple(
        (str(item[0]), item[1])
        for item in payload["metadata"]
    )
    confidence = payload["confidence"]
    if confidence is not None:
        confidence = float(confidence)
        if not 0 <= confidence <= 1:
            raise VerificationValidationError("Invalid record confidence.")
    return DetectionRecord(
        id=str(payload["id"]),
        element_class=element_class,
        geometry=geometry,
        bbox=bbox,
        confidence=confidence,
        detection_method=str(payload["detection_method"]),
        verification_status=(
            "verified"
            if payload.get("verification_status") == "verified"
            else "unverified"
        ),
        metadata=metadata,
    )
