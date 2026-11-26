"""Validate drawing upload names and sizes before decoding."""

from dataclasses import dataclass
from pathlib import PurePath

from config import load_settings
from utils.exceptions import DrawingValidationError


@dataclass(frozen=True)
class DrawingMetadata:
    """Basic metadata for a validated drawing upload."""

    filename: str
    extension: str
    size_bytes: int


def validate_drawing(filename: str, size_bytes: int) -> DrawingMetadata:
    """Validate a drawing's extension and non-empty size."""
    if size_bytes <= 0:
        raise DrawingValidationError("The uploaded drawing is empty.")

    extension = PurePath(filename).suffix.lower().lstrip(".")
    allowed_extensions = load_settings().supported_drawing_extensions
    if extension not in allowed_extensions:
        supported = ", ".join(item.upper() for item in allowed_extensions)
        raise DrawingValidationError(
            f"Unsupported drawing type. Use one of: {supported}."
        )

    return DrawingMetadata(
        filename=filename,
        extension=extension,
        size_bytes=size_bytes,
    )
