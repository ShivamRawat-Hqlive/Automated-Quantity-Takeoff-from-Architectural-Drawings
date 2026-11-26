"""PNG and JPEG image decoding and metadata extraction."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from utils.exceptions import DrawingValidationError

_SUPPORTED_FORMATS = {
    "png": "PNG",
    "jpg": "JPEG",
    "jpeg": "JPEG",
}


@dataclass(frozen=True)
class LoadedImage:
    """Decoded drawing preview and source image metadata."""

    image: Image.Image
    width: int
    height: int
    color_mode: str
    channels: int
    format: str


def load_image(image_bytes: bytes, filename: str) -> LoadedImage:
    """Decode a PNG or JPEG with Pillow and OpenCV without altering its source."""
    if not image_bytes:
        raise DrawingValidationError("The uploaded image is empty.")

    extension = PurePath(filename).suffix.lower().lstrip(".")
    expected_format = _SUPPORTED_FORMATS.get(extension)
    if expected_format is None:
        raise DrawingValidationError("Supported image types are PNG, JPG, and JPEG.")

    try:
        with Image.open(BytesIO(image_bytes)) as source:
            source.load()
            image_format = source.format
            color_mode = source.mode
            image = source.copy()
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError, ValueError) as exc:
        raise DrawingValidationError("The uploaded image is corrupted or unreadable.") from exc

    if image_format != expected_format:
        raise DrawingValidationError(
            f"The file extension does not match its {image_format or 'unknown'} image format."
        )

    try:
        decoded = cv2.imdecode(
            np.frombuffer(image_bytes, dtype=np.uint8),
            cv2.IMREAD_UNCHANGED,
        )
    except cv2.error as exc:
        raise DrawingValidationError("OpenCV could not decode the uploaded image.") from exc

    if decoded is None:
        raise DrawingValidationError("OpenCV could not decode the uploaded image.")

    channels = 1 if decoded.ndim == 2 else decoded.shape[2]
    return LoadedImage(
        image=image,
        width=image.width,
        height=image.height,
        color_mode=color_mode,
        channels=channels,
        format=image_format,
    )
