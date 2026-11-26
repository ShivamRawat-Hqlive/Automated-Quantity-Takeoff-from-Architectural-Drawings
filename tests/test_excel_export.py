from io import BytesIO

from openpyxl import load_workbook

from reports.excel_export import export_excel
from tests.test_report_data import make_snapshot


def test_excel_contains_required_sheets_and_formatting() -> None:
    workbook_bytes = export_excel(make_snapshot())
    workbook = load_workbook(BytesIO(workbook_bytes))

    assert workbook.sheetnames == [
        "Project Summary",
        "Detected Elements",
        "Wall Measurements",
        "Room Areas",
        "Verification Log",
        "Detailed BoQ",
        "Cost Summary",
        "Assumptions and Limitations",
    ]
    summary = workbook["Project Summary"]
    assert summary.freeze_panes == "A2"
    assert summary["A1"].value == "Field"
    assert summary["A1"].fill.fgColor.rgb.endswith("1F4E78")
    assert summary["B1"].value == "Value"

    boq = workbook["Detailed BoQ"]
    assert boq["F2"].number_format == '"₹"#,##0.00'
    assert boq["G2"].number_format == '"₹"#,##0.00'
    assert boq.max_row >= 3


def test_excel_totals_match_snapshot_cost() -> None:
    snapshot = make_snapshot()
    workbook = load_workbook(BytesIO(export_excel(snapshot)))
    cost_sheet = workbook["Cost Summary"]
    values = {
        cost_sheet.cell(row=row, column=1).value:
        cost_sheet.cell(row=row, column=2).value
        for row in range(2, cost_sheet.max_row + 1)
    }

    assert values["Subtotal"] == snapshot.cost.subtotal
    assert values["Grand Total"] == snapshot.cost.grand_total


def test_excel_statuses_preserve_verification_categories() -> None:
    workbook = load_workbook(BytesIO(export_excel(make_snapshot())))
    elements = workbook["Detected Elements"]
    statuses = {
        elements.cell(row=row, column=3).value
        for row in range(2, elements.max_row + 1)
    }

    assert "verified" in statuses
