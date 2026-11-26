from io import BytesIO

from openpyxl import load_workbook
from PIL import Image
import pymupdf

from boq.boq_generator import generate_boq
from boq.cost_estimator import calculate_costs
from detection.detector import create_record
from measurement.scale_calibration import calibrate_scale
from reports.excel_export import export_excel
from reports.pdf_export import export_pdf
from reports.report_data import build_report_snapshot
from verification.record_editor import edit_record
from verification.review_manager import ReviewManager


def test_corrected_review_updates_quantity_boq_and_both_reports() -> None:
    wall = create_record(
        record_id="wall-1",
        element_class="wall",
        geometry=((0, 0), (100, 0)),
        confidence=None,
        detection_method="synthetic",
    )
    rejected = create_record(
        record_id="wall-rejected",
        element_class="wall",
        geometry=((0, 20), (100, 20)),
        confidence=None,
        detection_method="synthetic",
    )
    manager = ReviewManager(
        (wall, rejected),
        source_width=200,
        source_height=200,
    )
    corrected = edit_record(
        wall,
        geometry=((0, 0), (150, 0)),
        source_width=200,
        source_height=200,
    )
    manager.edit_record("wall-1", corrected)
    manager.set_status("wall-1", "verified")
    manager.set_status("wall-rejected", "rejected")

    calibration = calibrate_scale(
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
    review = manager.snapshot()
    quantities = review.recalculated_quantities(calibration)
    assert quantities.summary.verified_wall_length_m == 1.5
    assert quantities.summary.unverified_wall_count == 0

    boq_items = generate_boq(quantities)
    assert len(boq_items) == 1
    assert boq_items[0].quantity == 1.5

    priced_items = tuple(
        __import__("dataclasses").replace(
            item,
            rate=100,
            total=item.quantity * 100,
            rate_source="user-entered",
        )
        for item in boq_items
    )
    cost = calculate_costs(
        priced_items,
        waste_percent=10,
        contingency_percent=5,
        tax_percent=18,
    )
    assert cost.subtotal == 150
    assert cost.grand_total == 204.435

    source = Image.new("RGB", (200, 200), "white")
    annotated = source.copy()
    snapshot = build_report_snapshot(
        project_name="Consistency Project",
        filename="drawing.png",
        file_size_bytes=100,
        source_image=source,
        annotated_image=annotated,
        quantities=quantities,
        review=review,
        boq_items=priced_items,
        cost=cost,
        calibration=calibration,
        source_width=200,
        source_height=200,
        coordinate_frame="source image pixels; origin at top-left",
    )

    workbook = load_workbook(BytesIO(export_excel(snapshot)))
    cost_sheet = workbook["Cost Summary"]
    cost_values = {
        cost_sheet.cell(row=row, column=1).value:
        cost_sheet.cell(row=row, column=2).value
        for row in range(2, cost_sheet.max_row + 1)
    }
    assert cost_values["Subtotal"] == quantities.summary.verified_wall_length_m * 100
    assert cost_values["Grand Total"] == cost.grand_total

    pdf_bytes = export_pdf(snapshot)
    pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text("text") for page in pdf)
    pdf.close()
    assert "204.44" in text
    assert "rejected" in text
    assert "wall-rejected" in text
