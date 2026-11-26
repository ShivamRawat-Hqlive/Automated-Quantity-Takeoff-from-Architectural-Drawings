import pytest

from ingestion.validation import validate_drawing
from utils.exceptions import DrawingValidationError


@pytest.mark.parametrize(
    ("filename", "expected_extension"),
    [
        ("floor-plan.PDF", "pdf"),
        ("level-1.png", "png"),
        ("elevation.jpeg", "jpeg"),
    ],
)
def test_validate_drawing_accepts_supported_extensions(
    filename: str, expected_extension: str
) -> None:
    drawing = validate_drawing(filename, 128)

    assert drawing.filename == filename
    assert drawing.extension == expected_extension
    assert drawing.size_bytes == 128


@pytest.mark.parametrize(
    ("filename", "size_bytes", "message"),
    [
        ("drawing.dwg", 128, "Unsupported drawing type"),
        ("floor-plan.pdf", 0, "empty"),
    ],
)
def test_validate_drawing_rejects_invalid_uploads(
    filename: str, size_bytes: int, message: str
) -> None:
    with pytest.raises(DrawingValidationError, match=message):
        validate_drawing(filename, size_bytes)
