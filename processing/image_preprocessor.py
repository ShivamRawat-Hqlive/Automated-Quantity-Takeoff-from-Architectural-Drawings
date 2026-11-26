"""Non-destructive image transformations for future drawing workflows."""

from dataclasses import dataclass
from math import atan2, degrees
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from utils.exceptions import DrawingProcessingError


@dataclass(frozen=True)
class LineCandidate:
    """A horizontal or vertical Hough line in source-image pixel coordinates."""

    orientation: Literal["horizontal", "vertical"]
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass(frozen=True)
class ImageAnalysis:
    """Image-processing outputs and their source-coordinate metadata."""

    grayscale: np.ndarray
    noise_reduced: np.ndarray
    binary_threshold: np.ndarray
    canny_edges: np.ndarray
    contours: tuple[tuple[tuple[int, int], ...], ...]
    horizontal_lines: tuple[LineCandidate, ...]
    vertical_lines: tuple[LineCandidate, ...]
    contour_overlay: np.ndarray
    line_overlay: np.ndarray
    source_width: int
    source_height: int
    coordinate_space: str
    parameters: tuple[tuple[str, int | float], ...]


def preprocess_image(
    image: Image.Image,
    *,
    grayscale: bool = False,
    max_dimension: int | None = None,
) -> Image.Image:
    """Return a transformed copy; the supplied drawing is never modified."""
    if max_dimension is not None and (
        not isinstance(max_dimension, int)
        or isinstance(max_dimension, bool)
        or max_dimension <= 0
    ):
        raise ValueError("max_dimension must be a positive integer.")

    result = image.copy()
    if grayscale:
        rgb_array = np.asarray(result.convert("RGB"))
        grayscale_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)
        result = Image.fromarray(grayscale_array)

    if max_dimension is not None and max(result.size) > max_dimension:
        scale = max_dimension / max(result.size)
        resized_size = (
            max(1, round(result.width * scale)),
            max(1, round(result.height * scale)),
        )
        result = result.resize(resized_size, Image.Resampling.LANCZOS)

    return result


def _validate_grayscale_image(image: np.ndarray) -> None:
    if image.ndim != 2 or image.dtype != np.uint8:
        raise ValueError("Expected a single-channel uint8 grayscale image.")


def reduce_gaussian_noise(
    grayscale: np.ndarray,
    *,
    kernel_size: int = 5,
    sigma: float = 0,
) -> np.ndarray:
    """Apply Gaussian blur to a grayscale image and return a new array."""
    _validate_grayscale_image(grayscale)
    if (
        not isinstance(kernel_size, int)
        or isinstance(kernel_size, bool)
        or kernel_size <= 0
        or kernel_size % 2 == 0
    ):
        raise ValueError("kernel_size must be a positive odd integer.")
    if sigma < 0:
        raise ValueError("sigma must be non-negative.")
    return cv2.GaussianBlur(grayscale, (kernel_size, kernel_size), sigma)


def adaptive_binary_threshold(
    grayscale: np.ndarray,
    *,
    block_size: int = 11,
    constant: int = 2,
) -> np.ndarray:
    """Create a binary image using a Gaussian adaptive threshold."""
    _validate_grayscale_image(grayscale)
    if (
        not isinstance(block_size, int)
        or isinstance(block_size, bool)
        or block_size <= 1
        or block_size % 2 == 0
    ):
        raise ValueError("block_size must be an odd integer greater than one.")
    return cv2.adaptiveThreshold(
        grayscale,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        constant,
    )


def canny_edge_detection(
    grayscale: np.ndarray,
    *,
    lower_threshold: int = 50,
    upper_threshold: int = 150,
) -> np.ndarray:
    """Detect Canny edges in a grayscale image."""
    _validate_grayscale_image(grayscale)
    if not 0 <= lower_threshold < upper_threshold <= 255:
        raise ValueError("Canny thresholds must satisfy 0 <= lower < upper <= 255.")
    return cv2.Canny(grayscale, lower_threshold, upper_threshold)


def find_contours(binary_image: np.ndarray) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Return contour points in the input image's pixel coordinate space."""
    _validate_grayscale_image(binary_image)
    found, _ = cv2.findContours(
        binary_image.copy(),
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    return tuple(
        tuple((int(point[0]), int(point[1])) for point in contour.reshape(-1, 2))
        for contour in found
    )


def find_hough_line_candidates(
    edges: np.ndarray,
    *,
    threshold: int = 30,
    min_line_length: int = 30,
    max_line_gap: int = 10,
    angle_tolerance: float = 10,
) -> tuple[LineCandidate, ...]:
    """Find horizontal and vertical line candidates from a Canny edge image."""
    _validate_grayscale_image(edges)
    if threshold <= 0 or min_line_length <= 0 or max_line_gap < 0:
        raise ValueError("Hough threshold and minimum length must be positive.")
    if not 0 <= angle_tolerance < 45:
        raise ValueError("angle_tolerance must be between 0 and 45 degrees.")

    detected = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=threshold,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )
    if detected is None:
        return ()

    candidates: list[LineCandidate] = []
    for x1, y1, x2, y2 in detected.reshape(-1, 4):
        angle = degrees(atan2(abs(int(y2) - int(y1)), abs(int(x2) - int(x1))))
        if angle <= angle_tolerance:
            orientation: Literal["horizontal", "vertical"] = "horizontal"
        elif angle >= 90 - angle_tolerance:
            orientation = "vertical"
        else:
            continue
        candidates.append(
            LineCandidate(
                orientation=orientation,
                start=(int(x1), int(y1)),
                end=(int(x2), int(y2)),
            )
        )
    return tuple(candidates)


def _analyze_image(image: Image.Image) -> ImageAnalysis:
    grayscale_image = preprocess_image(image, grayscale=True)
    grayscale = np.array(grayscale_image, dtype=np.uint8, copy=True)
    noise_reduced = reduce_gaussian_noise(grayscale)
    binary = adaptive_binary_threshold(noise_reduced)
    edges = canny_edge_detection(noise_reduced)
    contours = find_contours(binary)
    lines = find_hough_line_candidates(edges)

    contour_overlay = cv2.cvtColor(grayscale, cv2.COLOR_GRAY2RGB)
    if contours:
        contour_arrays = [
            np.asarray(contour, dtype=np.int32).reshape(-1, 1, 2)
            for contour in contours
        ]
        cv2.drawContours(contour_overlay, contour_arrays, -1, (0, 255, 0), 1)

    line_overlay = cv2.cvtColor(grayscale, cv2.COLOR_GRAY2RGB)
    for line in lines:
        color = (255, 0, 0) if line.orientation == "horizontal" else (0, 0, 255)
        cv2.line(line_overlay, line.start, line.end, color, 2)

    width, height = image.size
    return ImageAnalysis(
        grayscale=grayscale,
        noise_reduced=noise_reduced,
        binary_threshold=binary,
        canny_edges=edges,
        contours=contours,
        horizontal_lines=tuple(line for line in lines if line.orientation == "horizontal"),
        vertical_lines=tuple(line for line in lines if line.orientation == "vertical"),
        contour_overlay=contour_overlay,
        line_overlay=line_overlay,
        source_width=width,
        source_height=height,
        coordinate_space="source image pixels; origin at top-left",
        parameters=(
            ("gaussian_kernel_size", 5),
            ("adaptive_block_size", 11),
            ("adaptive_constant", 2),
            ("canny_lower_threshold", 50),
            ("canny_upper_threshold", 150),
            ("hough_threshold", 30),
            ("hough_min_line_length", 30),
            ("hough_max_line_gap", 10),
            ("line_angle_tolerance_degrees", 10),
        ),
    )


def analyze_image(image: Image.Image) -> ImageAnalysis:
    """Run non-destructive image processing and retain source pixel coordinates."""
    try:
        return _analyze_image(image)
    except cv2.error as exc:
        raise DrawingProcessingError("OpenCV could not process the drawing image.") from exc
