import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from processing.image_preprocessor import (
    adaptive_binary_threshold,
    analyze_image,
    canny_edge_detection,
    find_contours,
    find_hough_line_candidates,
    reduce_gaussian_noise,
)


def create_line_drawing() -> Image.Image:
    image = Image.new("RGB", (256, 192), "white")
    drawing = ImageDraw.Draw(image)
    drawing.line((20, 40, 230, 40), fill="black", width=3)
    drawing.line((60, 15, 60, 175), fill="black", width=3)
    drawing.rectangle((100, 80, 180, 150), outline="black", width=2)
    return image


def test_image_analysis_produces_expected_arrays_and_coordinates() -> None:
    image = create_line_drawing()
    original_pixels = np.asarray(image).copy()

    analysis = analyze_image(image)

    assert analysis.grayscale.shape == (192, 256)
    assert analysis.noise_reduced.shape == analysis.grayscale.shape
    assert analysis.binary_threshold.shape == analysis.grayscale.shape
    assert set(np.unique(analysis.binary_threshold)).issubset({0, 255})
    assert analysis.canny_edges.shape == analysis.grayscale.shape
    assert analysis.contours
    assert analysis.horizontal_lines
    assert analysis.vertical_lines
    assert analysis.source_width == 256
    assert analysis.source_height == 192
    assert analysis.coordinate_space == "source image pixels; origin at top-left"
    assert np.array_equal(np.asarray(image), original_pixels)


def test_processing_stages_return_new_arrays() -> None:
    grayscale = np.full((100, 120), 255, dtype=np.uint8)
    cv2.line(grayscale, (10, 30), (100, 30), 0, 3)
    original_pixels = grayscale.copy()

    denoised = reduce_gaussian_noise(grayscale)
    binary = adaptive_binary_threshold(denoised)
    edges = canny_edge_detection(denoised)
    contours = find_contours(binary)
    lines = find_hough_line_candidates(edges)

    assert denoised is not grayscale
    assert np.array_equal(grayscale, original_pixels)
    assert binary.shape == grayscale.shape
    assert edges.shape == grayscale.shape
    assert contours
    assert lines


@pytest.mark.parametrize("kernel_size", [0, 2])
def test_gaussian_filter_rejects_invalid_kernel_size(kernel_size: int) -> None:
    with pytest.raises(ValueError, match="positive odd integer"):
        reduce_gaussian_noise(np.zeros((10, 10), dtype=np.uint8), kernel_size=kernel_size)

