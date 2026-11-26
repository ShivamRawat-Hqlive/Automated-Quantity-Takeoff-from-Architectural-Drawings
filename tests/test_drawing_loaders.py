from io import BytesIO

import pymupdf
import pytest
from PIL import Image

from ingestion.image_loader import load_image
from ingestion.pdf_loader import inspect_pdf, render_pdf_page
from processing.image_preprocessor import preprocess_image
from utils.exceptions import DrawingValidationError


def create_pdf(page_count: int = 1) -> bytes:
    document = pymupdf.open()
    for _ in range(page_count):
        document.new_page(width=100, height=80)
    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()


def create_image(image_format: str) -> bytes:
    image = Image.new("RGB", (40, 20), color=(120, 80, 40))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_inspect_valid_single_page_pdf() -> None:
    info = inspect_pdf(create_pdf())

    assert info.page_count == 1


def test_inspect_and_render_multi_page_pdf() -> None:
    pdf_bytes = create_pdf(page_count=3)

    assert inspect_pdf(pdf_bytes).page_count == 3
    rendered = render_pdf_page(pdf_bytes, page_number=2, dpi=72)
    assert rendered.size == (100, 80)
    assert rendered.mode == "RGB"


@pytest.mark.parametrize(
    ("filename", "image_format"),
    [("plan.png", "PNG"), ("plan.jpg", "JPEG"), ("plan.jpeg", "JPEG")],
)
def test_load_png_and_jpg_images(filename: str, image_format: str) -> None:
    loaded = load_image(create_image(image_format), filename)

    assert (loaded.width, loaded.height) == (40, 20)
    assert loaded.color_mode == "RGB"
    assert loaded.channels == 3
    assert loaded.format == image_format


def test_inspect_corrupted_pdf_raises_validation_error() -> None:
    with pytest.raises(DrawingValidationError, match="readable PDF"):
        inspect_pdf(b"%PDF-1.7\nnot a valid PDF")


def test_load_corrupted_image_raises_validation_error() -> None:
    with pytest.raises(DrawingValidationError, match="corrupted or unreadable"):
        load_image(b"not an image", "plan.png")


def test_load_image_rejects_mismatched_extension() -> None:
    with pytest.raises(DrawingValidationError, match="extension does not match"):
        load_image(create_image("PNG"), "plan.jpg")


def test_render_pdf_rejects_page_outside_document() -> None:
    with pytest.raises(DrawingValidationError, match="between 1 and 1"):
        render_pdf_page(create_pdf(), page_number=2, dpi=72)


def test_preprocess_image_returns_transformed_copy() -> None:
    original = Image.new("RGB", (80, 40), color=(255, 0, 0))

    transformed = preprocess_image(
        original,
        grayscale=True,
        max_dimension=20,
    )

    assert transformed.size == (20, 10)
    assert transformed.mode == "L"
    assert original.size == (80, 40)
    assert original.mode == "RGB"
    assert original.getpixel((0, 0)) == (255, 0, 0)


def test_preprocess_image_requires_positive_max_dimension() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        preprocess_image(Image.new("RGB", (10, 10)), max_dimension=0)


def test_render_pdf_rejects_nonpositive_dpi() -> None:
    with pytest.raises(DrawingValidationError, match="positive integer"):
        render_pdf_page(create_pdf(), page_number=1, dpi=0)
