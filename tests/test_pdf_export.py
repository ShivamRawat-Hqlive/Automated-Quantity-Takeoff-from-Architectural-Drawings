from io import BytesIO

import pymupdf

from reports.pdf_export import export_pdf
from tests.test_report_data import make_snapshot


def test_pdf_is_valid_and_has_multiple_pages() -> None:
    pdf_bytes = export_pdf(make_snapshot())
    assert pdf_bytes.startswith(b"%PDF")

    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    assert document.page_count >= 4
    text = "\n".join(page.get_text("text") for page in document)
    document.close()

    assert "Quantity Takeoff Report" in text
    assert "Detailed BoQ" in text
    assert "Cost estimate" in text
    assert "Assumptions" in text


def test_pdf_includes_original_and_annotated_images() -> None:
    pdf_bytes = export_pdf(make_snapshot())
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    image_count = sum(len(page.get_images(full=True)) for page in document)
    text = "\n".join(page.get_text("text") for page in document)
    document.close()

    assert image_count >= 2
    assert "Original drawing" in text
    assert "Annotated drawing" in text


def test_pdf_missing_calibration_is_reported() -> None:
    snapshot = make_snapshot()
    from reports.report_data import build_report_snapshot

    missing = build_report_snapshot(
        project_name=snapshot.project_name,
        filename=snapshot.filename,
        file_size_bytes=snapshot.file_size_bytes,
        source_image=snapshot.source_image,
        annotated_image=snapshot.annotated_image,
        quantities=snapshot.quantities,
        review=snapshot.review,
        boq_items=snapshot.boq_items,
        cost=snapshot.cost,
        calibration=None,
        source_width=snapshot.source_width,
        source_height=snapshot.source_height,
        coordinate_frame=snapshot.coordinate_frame,
    )
    document = pymupdf.open(stream=export_pdf(missing), filetype="pdf")
    text = "\n".join(page.get_text("text") for page in document)
    document.close()

    assert "Missing" in text
