"""Immutable report snapshot shared by Excel and PDF exporters."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from PIL import Image

from boq.boq_generator import BoQItem
from boq.cost_estimator import CostBreakdown
from measurement.quantity_calculator import QuantityResult
from measurement.scale_calibration import ScaleCalibration
from verification.review_manager import ReviewSnapshot


@dataclass(frozen=True)
class CalibrationReportData:
    calibrated: bool
    source_width: int
    source_height: int
    coordinate_frame: str
    pixel_distance: float | None
    known_distance: float | None
    known_unit: str | None
    known_distance_metres: float | None
    pixels_per_metre: float | None
    metres_per_pixel: float | None


@dataclass(frozen=True)
class ProjectReportData:
    project_name: str
    filename: str
    file_size_bytes: int
    generation_timestamp: str
    source_image: Image.Image
    annotated_image: Image.Image
    source_width: int
    source_height: int
    coordinate_frame: str
    calibration: CalibrationReportData
    quantities: QuantityResult
    review: ReviewSnapshot
    boq_items: tuple[BoQItem, ...]
    cost: CostBreakdown
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    currency: Literal["INR"]


def build_calibration_report_data(
    calibration: ScaleCalibration | None,
    *,
    source_width: int,
    source_height: int,
    coordinate_frame: str,
) -> CalibrationReportData:
    if calibration is None:
        return CalibrationReportData(
            calibrated=False,
            source_width=source_width,
            source_height=source_height,
            coordinate_frame=coordinate_frame,
            pixel_distance=None,
            known_distance=None,
            known_unit=None,
            known_distance_metres=None,
            pixels_per_metre=None,
            metres_per_pixel=None,
        )
    return CalibrationReportData(
        calibrated=True,
        source_width=source_width,
        source_height=source_height,
        coordinate_frame=coordinate_frame,
        pixel_distance=calibration.pixel_distance,
        known_distance=calibration.known_distance,
        known_unit=calibration.known_unit,
        known_distance_metres=calibration.known_distance_metres,
        pixels_per_metre=calibration.pixels_per_metre,
        metres_per_pixel=calibration.metres_per_pixel,
    )


def build_report_snapshot(
    *,
    project_name: str,
    filename: str,
    file_size_bytes: int,
    source_image: Image.Image,
    annotated_image: Image.Image,
    quantities: QuantityResult,
    review: ReviewSnapshot,
    boq_items: tuple[BoQItem, ...],
    cost: CostBreakdown,
    calibration: ScaleCalibration | None,
    source_width: int,
    source_height: int,
    coordinate_frame: str,
) -> ProjectReportData:
    if not project_name.strip():
        raise ValueError("Project name is required.")
    if not filename.strip():
        raise ValueError("Source filename is required.")
    if file_size_bytes < 0:
        raise ValueError("File size cannot be negative.")
    if source_image.size != (source_width, source_height):
        raise ValueError("Original image dimensions do not match the source raster.")
    if annotated_image.size != (source_width, source_height):
        raise ValueError("Annotated image dimensions do not match the source raster.")
    if cost.currency != "INR":
        raise ValueError("This report snapshot requires INR currency.")

    assumptions = (
        "All wall and room quantities are derived from the supplied source raster.",
        "Only reviewed verified or manual records are included in verified totals.",
        "Rejected and unverified records are separated from verified totals.",
        "Missing or zero rates are identified and are not inferred market prices.",
        "Waste, contingency and tax are percentage-based additions.",
    )
    limitations = (
        "No AI or YOLO construction-element detection is performed.",
        "Door/window and wall/room geometry remains rule-based candidate data until human review.",
        "Real-world accuracy depends on the two-point calibration entered by the user.",
        "No OCR, real-world 1:100 assumption, cost database or tax-jurisdiction lookup is used.",
        "PDF-point coordinates are not mixed with raster-pixel measurements.",
    )
    return ProjectReportData(
        project_name=project_name,
        filename=filename,
        file_size_bytes=file_size_bytes,
        generation_timestamp=datetime.now(timezone.utc).isoformat(),
        source_image=source_image.copy(),
        annotated_image=annotated_image.copy(),
        source_width=source_width,
        source_height=source_height,
        coordinate_frame=coordinate_frame,
        calibration=build_calibration_report_data(
            calibration,
            source_width=source_width,
            source_height=source_height,
            coordinate_frame=coordinate_frame,
        ),
        quantities=quantities,
        review=review,
        boq_items=boq_items,
        cost=cost,
        assumptions=assumptions,
        limitations=limitations,
        currency="INR",
    )
