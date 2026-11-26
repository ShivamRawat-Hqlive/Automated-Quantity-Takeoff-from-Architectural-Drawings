from io import BytesIO

import pymupdf
from PIL import Image, ImageDraw

from processing.pdf_extractor import extract_pdf


def create_vector_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    page.insert_text((20, 25), "Level 1 plan", fontsize=12)
    page.draw_line((15, 50), (180, 50), color=(0, 0, 0), width=1)
    page.draw_rect(pymupdf.Rect(20, 60, 100, 100), color=(0, 0, 0), width=1)
    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()


def create_scanned_pdf() -> bytes:
    scan = Image.new("RGB", (200, 120), "white")
    ImageDraw.Draw(scan).rectangle((20, 20, 180, 100), outline="black", width=2)
    image_bytes = BytesIO()
    scan.save(image_bytes, format="PNG")

    document = pymupdf.open()
    page = document.new_page(width=200, height=120)
    page.insert_image(page.rect, stream=image_bytes.getvalue())
    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()


def create_empty_pdf() -> bytes:
    document = pymupdf.open()
    document.new_page(width=200, height=120)
    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()


def create_mixed_pdf() -> bytes:
    scan = Image.new("RGB", (200, 120), "white")
    image_bytes = BytesIO()
    scan.save(image_bytes, format="PNG")

    document = pymupdf.open()
    vector_page = document.new_page(width=200, height=120)
    vector_page.draw_line((10, 10), (190, 10))
    scanned_page = document.new_page(width=200, height=120)
    scanned_page.insert_image(scanned_page.rect, stream=image_bytes.getvalue())
    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()


def test_extract_vector_pdf_text_and_geometry_with_coordinates() -> None:
    extraction = extract_pdf(create_vector_pdf())
    page = extraction.pages[0]

    assert extraction.page_count == 1
    assert extraction.content_type == "vector"
    assert extraction.extraction_method == "PyMuPDF"
    assert page.text == "Level 1 plan"
    assert page.text_blocks
    assert page.vector_paths
    assert page.embedded_images == ()
    assert page.width_points == 200
    assert page.height_points == 120
    assert page.coordinate_space == "PDF page points; origin at top-left"
    assert any(path.bbox == (20.0, 60.0, 100.0, 100.0) for path in page.vector_paths)
    assert all(block.bbox[0] >= 0 and block.bbox[1] >= 0 for block in page.text_blocks)


def test_extract_scanned_pdf_without_text_or_vectors() -> None:
    extraction = extract_pdf(create_scanned_pdf())
    page = extraction.pages[0]

    assert extraction.content_type == "scanned"
    assert page.content_type == "scanned"
    assert page.text == ""
    assert page.text_blocks == ()
    assert page.vector_paths == ()
    assert len(page.embedded_images) == 1
    assert page.embedded_images[0].bbox == (0.0, 0.0, 200.0, 120.0)


def test_extract_empty_pdf_page_without_text_or_vectors() -> None:
    extraction = extract_pdf(create_empty_pdf())
    page = extraction.pages[0]

    assert extraction.content_type == "unknown"
    assert page.text == ""
    assert page.text_blocks == ()
    assert page.vector_paths == ()
    assert page.embedded_images == ()


def test_extract_mixed_document_classification() -> None:
    extraction = extract_pdf(create_mixed_pdf())

    assert extraction.content_type == "mixed"
    assert [page.content_type for page in extraction.pages] == ["vector", "scanned"]
