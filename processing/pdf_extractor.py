"""Coordinate-aware text, vector, and image extraction from PDFs."""

from dataclasses import dataclass
from typing import Literal

import pymupdf as fitz

from ingestion.pdf_loader import open_pdf_document
from utils.exceptions import DrawingProcessingError, DrawingValidationError

PdfContentType = Literal["scanned", "vector", "mixed", "unknown"]


@dataclass(frozen=True)
class TextBlock:
    """Extracted text and its bounding box in PDF page points."""

    bbox: tuple[float, float, float, float]
    text: str


@dataclass(frozen=True)
class VectorCommand:
    """A PyMuPDF vector path command and its numeric page coordinates."""

    operation: str
    coordinates: tuple[float, ...]


@dataclass(frozen=True)
class VectorPath:
    """An extracted vector drawing path and its style metadata."""

    bbox: tuple[float, float, float, float]
    commands: tuple[VectorCommand, ...]
    stroke_color: tuple[float, ...] | None
    fill_color: tuple[float, ...] | None
    stroke_width: float | None


@dataclass(frozen=True)
class EmbeddedImage:
    """Image metadata and placement in PDF page coordinates."""

    xref: int
    width: int
    height: int
    bits_per_component: int
    color_space: str | None
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class PdfPageExtraction:
    """Extracted content for one page, with coordinates in PDF points."""

    page_number: int
    width_points: float
    height_points: float
    rotation: int
    text: str
    text_blocks: tuple[TextBlock, ...]
    vector_paths: tuple[VectorPath, ...]
    embedded_images: tuple[EmbeddedImage, ...]
    content_type: PdfContentType
    coordinate_space: str


@dataclass(frozen=True)
class PdfExtraction:
    """Document-wide extraction results and content classification."""

    page_count: int
    content_type: PdfContentType
    pages: tuple[PdfPageExtraction, ...]
    extraction_method: str


def _bbox(values: object) -> tuple[float, float, float, float]:
    if isinstance(values, fitz.Rect):
        return (
            float(values.x0),
            float(values.y0),
            float(values.x1),
            float(values.y1),
        )
    if isinstance(values, (tuple, list)) and len(values) == 4:
        x0, y0, x1, y1 = values
        return float(x0), float(y0), float(x1), float(y1)
    raise DrawingProcessingError("PDF content returned an invalid bounding box.")


def _coordinates(value: object) -> tuple[float, ...]:
    if isinstance(value, fitz.Point):
        return float(value.x), float(value.y)
    if isinstance(value, fitz.Rect):
        return float(value.x0), float(value.y0), float(value.x1), float(value.y1)
    if isinstance(value, fitz.Quad):
        return tuple(
            coordinate
            for point in (value.ul, value.ur, value.ll, value.lr)
            for coordinate in (float(point.x), float(point.y))
        )
    if isinstance(value, (tuple, list)):
        return tuple(
            coordinate
            for item in value
            for coordinate in _coordinates(item)
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (float(value),)
    return ()


def _color(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return tuple(float(channel) for channel in value)
    raise DrawingProcessingError("PDF content returned invalid vector color metadata.")


def _extract_text_blocks(page: fitz.Page) -> tuple[TextBlock, ...]:
    page_dictionary = page.get_text("dict")
    text_blocks: list[TextBlock] = []
    for block in page_dictionary.get("blocks", []):
        if block.get("type") != 0:
            continue
        text = "\n".join(
            "".join(span.get("text", "") for span in line.get("spans", []))
            for line in block.get("lines", [])
        ).strip()
        if text:
            text_blocks.append(TextBlock(bbox=_bbox(block["bbox"]), text=text))
    return tuple(text_blocks)


def _extract_vector_paths(page: fitz.Page) -> tuple[VectorPath, ...]:
    paths: list[VectorPath] = []
    for drawing in page.get_drawings():
        commands = tuple(
            VectorCommand(
                operation=str(item[0]),
                coordinates=tuple(
                    coordinate
                    for value in item[1:]
                    for coordinate in _coordinates(value)
                ),
            )
            for item in drawing.get("items", [])
        )
        paths.append(
            VectorPath(
                bbox=_bbox(drawing["rect"]),
                commands=commands,
                stroke_color=_color(drawing.get("color")),
                fill_color=_color(drawing.get("fill")),
                stroke_width=(
                    float(drawing["width"])
                    if drawing.get("width") is not None
                    else None
                ),
            )
        )
    return tuple(paths)


def _extract_embedded_images(page: fitz.Page) -> tuple[EmbeddedImage, ...]:
    images: list[EmbeddedImage] = []
    for image in page.get_image_info(xrefs=True):
        images.append(
            EmbeddedImage(
                xref=int(image.get("xref", 0)),
                width=int(image.get("width", 0)),
                height=int(image.get("height", 0)),
                bits_per_component=int(image.get("bpc", 0)),
                color_space=image.get("cs-name"),
                bbox=_bbox(image["bbox"]),
            )
        )
    return tuple(images)


def _classify_page(
    text: str,
    vector_paths: tuple[VectorPath, ...],
    embedded_images: tuple[EmbeddedImage, ...],
) -> PdfContentType:
    has_raster_content = bool(embedded_images)
    has_native_content = bool(text.strip() or vector_paths)
    if has_raster_content and has_native_content:
        return "mixed"
    if has_raster_content:
        return "scanned"
    if has_native_content:
        return "vector"
    return "unknown"


def _extract_page(page: fitz.Page, page_number: int) -> PdfPageExtraction:
    text = page.get_text("text").strip()
    text_blocks = _extract_text_blocks(page)
    vector_paths = _extract_vector_paths(page)
    embedded_images = _extract_embedded_images(page)
    return PdfPageExtraction(
        page_number=page_number,
        width_points=float(page.rect.width),
        height_points=float(page.rect.height),
        rotation=int(page.rotation),
        text=text,
        text_blocks=text_blocks,
        vector_paths=vector_paths,
        embedded_images=embedded_images,
        content_type=_classify_page(text, vector_paths, embedded_images),
        coordinate_space="PDF page points; origin at top-left",
    )


def _classify_document(pages: tuple[PdfPageExtraction, ...]) -> PdfContentType:
    page_types = {page.content_type for page in pages}
    page_types.discard("unknown")
    if not page_types:
        return "unknown"
    if "mixed" in page_types or len(page_types) > 1:
        return "mixed"
    return next(iter(page_types))


def extract_pdf(pdf_bytes: bytes) -> PdfExtraction:
    """Extract text, vectors, and embedded-image metadata without altering the PDF."""
    try:
        with open_pdf_document(pdf_bytes) as document:
            if document.page_count == 0:
                raise DrawingValidationError("The PDF contains no pages.")
            pages = tuple(
                _extract_page(document.load_page(index), index + 1)
                for index in range(document.page_count)
            )
    except DrawingValidationError:
        raise
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise DrawingProcessingError("Could not extract content from the PDF.") from exc

    return PdfExtraction(
        page_count=len(pages),
        content_type=_classify_document(pages),
        pages=pages,
        extraction_method="PyMuPDF",
    )
