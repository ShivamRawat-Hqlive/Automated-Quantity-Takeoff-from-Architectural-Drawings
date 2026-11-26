"""Excel workbook export using one immutable report snapshot."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from reports.report_data import ProjectReportData


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
SUBTOTAL_FILL = PatternFill("solid", fgColor="D9EAF7")
THIN_BORDER = Border(
    left=Side(style="thin", color="B7C9D6"),
    right=Side(style="thin", color="B7C9D6"),
    top=Side(style="thin", color="B7C9D6"),
    bottom=Side(style="thin", color="B7C9D6"),
)


def _sheet(workbook: Workbook, title: str):
    sheet = workbook.create_sheet(title)
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"
    return sheet


def _write_table(
    sheet,
    headers: tuple[str, ...],
    rows: tuple[tuple, ...],
    table_name: str,
) -> None:
    sheet.append(list(headers))
    for header_cell in sheet[1]:
        header_cell.fill = HEADER_FILL
        header_cell.font = HEADER_FONT
        header_cell.border = THIN_BORDER
        header_cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in rows:
        sheet.append(list(row))
    for row in sheet.iter_rows():
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top")
    for column in range(1, sheet.max_column + 1):
        values = [
            len(str(sheet.cell(row=row, column=column).value or ""))
            for row in range(1, sheet.max_row + 1)
        ]
        sheet.column_dimensions[get_column_letter(column)].width = min(
            max(values, default=10) + 2,
            50,
        )
    if sheet.max_row >= 2 and sheet.max_column >= 1:
        safe_name = "".join(
            character
            for character in table_name
            if character.isalnum()
        )
        table = Table(
            displayName=safe_name or "ReportTable",
            ref=f"A1:{get_column_letter(sheet.max_column)}{sheet.max_row}",
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)


def _key_value_sheet(sheet, title: str, rows: tuple[tuple[str, object], ...]) -> None:
    sheet.append(("Field", "Value"))
    for header in sheet[1]:
        header.fill = HEADER_FILL
        header.font = HEADER_FONT
        header.border = THIN_BORDER
    for row in rows:
        sheet.append(row)
    for row in sheet.iter_rows():
        for cell in row:
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.column_dimensions["A"].width = 28
    sheet.column_dimensions["B"].width = 80


def export_excel(snapshot: ProjectReportData) -> bytes:
    """Build the workbook entirely from an existing report snapshot."""
    workbook = Workbook()
    workbook.remove(workbook.active)

    summary = _sheet(workbook, "Project Summary")
    calibration = snapshot.calibration
    calibration_rows = (
        ("Project name", snapshot.project_name),
        ("Source filename", snapshot.filename),
        ("Source size bytes", snapshot.file_size_bytes),
        ("Source raster", f"{snapshot.source_width} x {snapshot.source_height} px"),
        ("Coordinate frame", snapshot.coordinate_frame),
        ("Generated at", snapshot.generation_timestamp),
        ("Currency", snapshot.currency),
        ("Calibration status", "Calibrated" if calibration.calibrated else "Missing"),
        ("Pixels per metre", calibration.pixels_per_metre),
        ("Metres per pixel", calibration.metres_per_pixel),
        ("Known distance", calibration.known_distance),
        ("Known unit", calibration.known_unit),
    )
    _key_value_sheet(summary, "Project Summary", calibration_rows)

    elements = _sheet(workbook, "Detected Elements")
    element_rows = tuple(
        (
            record.corrected.id,
            record.corrected.element_class,
            record.status,
            record.source,
            repr(record.corrected.geometry),
            repr(record.corrected.bbox),
            record.corrected.confidence,
            record.corrected.detection_method,
            record.correction_note,
        )
        for record in snapshot.review.records
    )
    _write_table(
        elements,
        (
            "ID",
            "Class",
            "Status",
            "Source",
            "Geometry",
            "BBox",
            "Confidence",
            "Detection Method",
            "Correction Note",
        ),
        element_rows,
        "DetectedElements",
    )

    walls = _sheet(workbook, "Wall Measurements")
    wall_rows = tuple(
        (
            wall.id,
            wall.length_px,
            wall.length_m,
            wall.thickness_px,
            wall.thickness_m,
            wall.status,
            wall.quantity_type,
        )
        for wall in snapshot.quantities.walls
    )
    _write_table(
        walls,
        (
            "ID",
            "Length px",
            "Length m",
            "Thickness px",
            "Thickness m",
            "Status",
            "Quantity Type",
        ),
        wall_rows,
        "WallMeasurements",
    )
    for row in range(2, walls.max_row + 1):
        walls.cell(row=row, column=2).number_format = "0.00"
        walls.cell(row=row, column=3).number_format = "0.000"
        walls.cell(row=row, column=4).number_format = "0"
        walls.cell(row=row, column=5).number_format = "0.000"

    rooms = _sheet(workbook, "Room Areas")
    room_rows = tuple(
        (
            room.id,
            room.area_px2,
            room.area_m2,
            room.perimeter_px,
            room.perimeter_m,
            room.status,
            room.quantity_type,
        )
        for room in snapshot.quantities.rooms
    )
    _write_table(
        rooms,
        (
            "ID",
            "Area px2",
            "Area m2",
            "Perimeter px",
            "Perimeter m",
            "Status",
            "Quantity Type",
        ),
        room_rows,
        "RoomAreas",
    )
    for row in range(2, rooms.max_row + 1):
        rooms.cell(row=row, column=2).number_format = "0.00"
        rooms.cell(row=row, column=3).number_format = "0.000"
        rooms.cell(row=row, column=4).number_format = "0.00"
        rooms.cell(row=row, column=5).number_format = "0.000"

    verification = _sheet(workbook, "Verification Log")
    verification_rows = tuple(
        (
            event.record_id,
            event.action,
            event.before_status,
            event.after_status,
            event.note,
            event.timestamp,
        )
        for event in snapshot.review.audit_history
    )
    _write_table(
        verification,
        ("Record ID", "Action", "Before", "After", "Note", "Timestamp"),
        verification_rows,
        "VerificationLog",
    )

    boq = _sheet(workbook, "Detailed BoQ")
    boq_rows = tuple(
        (
            item.item_id,
            item.name,
            item.description,
            item.quantity,
            item.unit,
            item.rate,
            item.total,
            item.status,
            item.rate_source,
        )
        for item in snapshot.boq_items
    )
    _write_table(
        boq,
        (
            "Item ID",
            "Name",
            "Description",
            "Quantity",
            "Unit",
            "Rate INR",
            "Total INR",
            "Status",
            "Rate Source",
        ),
        boq_rows,
        "DetailedBoQ",
    )
    for row in range(2, boq.max_row + 1):
        boq.cell(row=row, column=4).number_format = "0.000"
        boq.cell(row=row, column=6).number_format = '"₹"#,##0.00'
        boq.cell(row=row, column=7).number_format = '"₹"#,##0.00'
    if boq.max_row >= 2:
        total_row = boq.max_row + 1
        boq.cell(total_row, 6, "Subtotal")
        boq.cell(total_row, 7, snapshot.cost.subtotal)
        for cell in boq[total_row]:
            cell.fill = SUBTOTAL_FILL
            cell.border = THIN_BORDER
            cell.font = Font(bold=True)
        boq.cell(total_row, 7).number_format = '"₹"#,##0.00'

    costs = _sheet(workbook, "Cost Summary")
    cost_rows = (
        ("Subtotal", snapshot.cost.subtotal),
        ("Waste", snapshot.cost.waste_amount),
        ("Contingency", snapshot.cost.contingency_amount),
        ("Tax", snapshot.cost.tax_amount),
        ("Grand Total", snapshot.cost.grand_total),
        ("Currency", snapshot.cost.currency),
        ("Missing/zero-rate items", ", ".join(snapshot.cost.missing_rate_item_ids) or "None"),
    )
    _key_value_sheet(costs, "Cost Summary", cost_rows)
    for row in range(2, 7):
        costs.cell(row=row, column=2).number_format = '"₹"#,##0.00'

    assumptions = _sheet(workbook, "Assumptions and Limitations")
    assumptions_rows = tuple(
        ("Assumption", text)
        for text in snapshot.assumptions
    ) + tuple(
        ("Limitation", text)
        for text in snapshot.limitations
    )
    _key_value_sheet(assumptions, "Assumptions and Limitations", assumptions_rows)

    for sheet in workbook.worksheets:
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        if sheet.max_row >= 2 and sheet.max_column >= 1:
            sheet.conditional_formatting.add(
                f"A2:{get_column_letter(sheet.max_column)}{sheet.max_row}",
                FormulaRule(
                    formula=["ISBLANK(A2)"],
                    fill=PatternFill("solid", fgColor="FFF2CC"),
                ),
            )

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
