"""Multi-page PDF report export using one immutable report snapshot."""

from io import BytesIO

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image as ReportLabImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reports.report_data import ProjectReportData


def _fit_image(image: Image.Image, max_width: float, max_height: float) -> ReportLabImage:
    copy = image.copy()
    copy.thumbnail(
        (max(int(max_width), 1), max(int(max_height), 1)),
        Image.Resampling.LANCZOS,
    )
    output = BytesIO()
    copy.save(output, format="PNG")
    output.seek(0)
    rendered = ReportLabImage(output, width=max_width, height=max_height)
    rendered.drawWidth = copy.width
    rendered.drawHeight = copy.height
    return rendered


def _money(value: float) -> str:
    return f"₹{value:,.2f}"


def _table(
    headers: tuple[str, ...],
    rows: tuple[tuple, ...],
    available_width: float,
) -> Table:
    data = [list(headers)]
    data.extend([list(row) for row in rows])
    column_width = available_width / max(1, len(headers))
    table = Table(data, repeatRows=1, colWidths=[column_width] * len(headers))
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C9D6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF4F8")]),
            ]
        )
    )
    return table


def _header_footer(canvas: canvas.Canvas, doc: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#55616D"))
    canvas.drawString(doc.leftMargin, 10 * mm, "Automated Quantity Takeoff Report")
    canvas.drawRightString(
        doc.pagesize[0] - doc.rightMargin,
        10 * mm,
        f"Page {doc.page}",
    )
    canvas.restoreState()


def export_pdf(snapshot: ProjectReportData) -> bytes:
    """Build a paginated PDF entirely from an existing report snapshot."""
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{snapshot.project_name} Quantity Takeoff Report",
    )
    styles = getSampleStyleSheet()
    story = []

    cover = Paragraph(
        f"<b>{snapshot.project_name}</b><br/><font size='14'>Quantity Takeoff Report</font>",
        styles["Title"],
    )
    story.append(Spacer(1, 55 * mm))
    story.append(cover)
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            f"Source: {snapshot.filename}<br/>"
            f"Generated: {snapshot.generation_timestamp}",
            styles["Normal"],
        )
    )
    story.append(PageBreak())

    story.append(Paragraph("Project information", styles["Heading1"]))
    project_rows = (
        ("Project name", snapshot.project_name),
        ("Source filename", snapshot.filename),
        ("Source file size", f"{snapshot.file_size_bytes:,} bytes"),
        ("Source raster", f"{snapshot.source_width} x {snapshot.source_height} px"),
        ("Coordinate frame", snapshot.coordinate_frame),
        ("Calibration", "Available" if snapshot.calibration.calibrated else "Missing"),
        ("Currency", snapshot.currency),
    )
    story.append(_table(("Field", "Value"), project_rows, 182 * mm))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Drawing images", styles["Heading1"]))
    max_width = 182 * mm
    max_height = 95 * mm
    story.append(Paragraph("Original drawing", styles["Heading2"]))
    story.append(_fit_image(snapshot.source_image, max_width, max_height))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Annotated drawing", styles["Heading2"]))
    story.append(_fit_image(snapshot.annotated_image, max_width, max_height))
    story.append(PageBreak())

    story.append(Paragraph("Element summary", styles["Heading1"]))
    statistics = snapshot.review.statistics()
    element_rows = (
        ("Verified", statistics["verified"]),
        ("Unverified", statistics["unverified"]),
        ("Rejected", statistics["rejected"]),
        ("Manual", statistics["manual"]),
        ("Total", statistics["total"]),
    )
    story.append(_table(("Status", "Count"), element_rows, 182 * mm))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Wall measurements", styles["Heading1"]))
    wall_rows = tuple(
        (
            wall.id,
            f"{wall.length_px:.2f} px",
            "Not calibrated" if wall.length_m is None else f"{wall.length_m:.3f} m",
            wall.status,
        )
        for wall in snapshot.quantities.walls
    )
    story.append(
        _table(("ID", "Length px", "Length", "Status"), wall_rows, 182 * mm)
        if wall_rows
        else Paragraph("No wall measurements are available.", styles["Normal"])
    )
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Room areas", styles["Heading1"]))
    room_rows = tuple(
        (
            room.id,
            f"{room.area_px2:.2f} px2",
            "Not calibrated" if room.area_m2 is None else f"{room.area_m2:.3f} m2",
            room.status,
        )
        for room in snapshot.quantities.rooms
    )
    story.append(
        _table(("ID", "Area px2", "Area", "Status"), room_rows, 182 * mm)
        if room_rows
        else Paragraph("No room areas are available.", styles["Normal"])
    )
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Verification summary", styles["Heading1"]))
    verification_rows = tuple(
        (
            record.corrected.id,
            record.corrected.element_class,
            record.status,
            record.source,
            record.correction_note or "-",
        )
        for record in snapshot.review.records
    )
    story.append(
        _table(
            ("ID", "Class", "Status", "Source", "Correction Note"),
            verification_rows,
            182 * mm,
        )
        if verification_rows
        else Paragraph("No review records are available.", styles["Normal"])
    )
    story.append(PageBreak())

    story.append(Paragraph("Detailed BoQ", styles["Heading1"]))
    boq_rows = tuple(
        (
            item.item_id,
            item.name,
            f"{item.quantity:.3f}",
            item.unit,
            _money(item.rate),
            _money(item.total),
            item.status,
        )
        for item in snapshot.boq_items
    )
    story.append(
        _table(
            ("ID", "Name", "Quantity", "Unit", "Rate INR", "Total INR", "Status"),
            boq_rows,
            182 * mm,
        )
        if boq_rows
        else Paragraph("No BoQ items are available.", styles["Normal"])
    )
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Cost estimate", styles["Heading1"]))
    cost_rows = (
        ("Subtotal", _money(snapshot.cost.subtotal)),
        ("Waste", _money(snapshot.cost.waste_amount)),
        ("Contingency", _money(snapshot.cost.contingency_amount)),
        ("Tax", _money(snapshot.cost.tax_amount)),
        ("Grand total", _money(snapshot.cost.grand_total)),
        ("Missing/zero-rate items", ", ".join(snapshot.cost.missing_rate_item_ids) or "None"),
    )
    story.append(_table(("Item", "Value"), cost_rows, 182 * mm))
    story.append(PageBreak())

    story.append(Paragraph("Assumptions", styles["Heading1"]))
    for text in snapshot.assumptions:
        story.append(Paragraph(f"- {text}", styles["Normal"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Limitations", styles["Heading1"]))
    for text in snapshot.limitations:
        story.append(Paragraph(f"- {text}", styles["Normal"]))

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return output.getvalue()
