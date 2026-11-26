"""PDF inspection and page rendering using PyMuPDF."""

from dataclasses import dataclass

import pymupdf as fitz
from PIL import Image

from utils.exceptions import DrawingProcessingError, DrawingValidationError


@dataclass(frozen=True)
class PdfInfo:
    """Basic information extracted from a PDF drawing."""

    page_count: int


def open_pdf_document(pdf_bytes: bytes) -> fitz.Document:
    """Open a validated PDF; callers should use it as a context manager."""
    if not pdf_bytes:
        raise DrawingValidationError("The uploaded PDF is empty.")

    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError) as exc:
        raise DrawingValidationError("The uploaded file is not a readable PDF.") from exc

    if document.needs_pass:
        document.close()
        raise DrawingValidationError("Password-protected PDFs are not supported.")
    return document


def inspect_pdf(pdf_bytes: bytes) -> PdfInfo:
    """Read PDF metadata without changing or saving the source bytes."""
    with open_pdf_document(pdf_bytes) as document:
        page_count = document.page_count
        if page_count == 0:
            raise DrawingValidationError("The PDF contains no pages.")
        return PdfInfo(page_count=page_count)


def render_pdf_page(
    pdf_bytes: bytes,
    page_number: int,
    dpi: int = 300,
) -> Image.Image:
    """Render a one-based PDF page number to an RGB image."""
    if not isinstance(dpi, int) or isinstance(dpi, bool) or dpi <= 0:
        raise DrawingValidationError("DPI must be a positive integer.")
    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or page_number < 1
    ):
        raise DrawingValidationError("Page number must be a positive integer.")

    try:
        with open_pdf_document(pdf_bytes) as document:
            if page_number < 1 or page_number > document.page_count:
                raise DrawingValidationError(
                    f"Page number must be between 1 and {document.page_count}."
                )
            page = document.load_page(page_number - 1)
            scale = dpi / 72
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                colorspace=fitz.csRGB,
                alpha=False,
            )
            return Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
    except DrawingValidationError:
        raise
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise DrawingProcessingError(
            f"Could not render PDF page {page_number}."
        ) from exc
