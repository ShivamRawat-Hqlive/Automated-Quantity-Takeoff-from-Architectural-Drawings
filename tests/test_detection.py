from dataclasses import replace

from PIL import Image, ImageDraw

from detection.detector import run_all_detectors
from detection.door_detector import detect_doors
from detection.room_detector import detect_rooms
from detection.wall_detector import detect_walls, merge_wall_segments
from detection.window_detector import detect_windows
from processing.image_preprocessor import ImageAnalysis, LineCandidate, analyze_image


def create_drawing(
    *,
    door_symbol: bool = False,
    window_symbol: bool = False,
    open_room: bool = False,
) -> Image.Image:
    image = Image.new("RGB", (256, 192), "white")
    draw = ImageDraw.Draw(image)

    if open_room:
        draw.line((20, 20, 230, 20), fill="black", width=4)
        draw.line((20, 20, 20, 170), fill="black", width=4)
        draw.line((20, 170, 230, 170), fill="black", width=4)
        draw.line((230, 20, 230, 80), fill="black", width=4)
        draw.line((230, 110, 230, 170), fill="black", width=4)
        return image

    if door_symbol:
        draw.line((20, 100, 100, 100), fill="black", width=4)
        draw.line((140, 100, 230, 100), fill="black", width=4)
        draw.line((100, 100, 100, 60), fill="black", width=3)
        draw.arc((60, 60, 140, 140), start=270, end=360, fill="black", width=2)
    elif window_symbol:
        draw.line((20, 100, 100, 100), fill="black", width=4)
        draw.line((140, 100, 230, 100), fill="black", width=4)
        draw.line((100, 94, 140, 94), fill="black", width=2)
        draw.line((100, 106, 140, 106), fill="black", width=2)
    else:
        draw.rectangle((20, 20, 230, 170), outline="black", width=4)
    return image


def create_analysis(image: Image.Image) -> ImageAnalysis:
    return analyze_image(image)


def replace_analysis_lines(
    analysis: ImageAnalysis,
    *,
    horizontal: tuple[LineCandidate, ...],
    vertical: tuple[LineCandidate, ...] = (),
) -> ImageAnalysis:
    return replace(
        analysis,
        horizontal_lines=horizontal,
        vertical_lines=vertical,
    )


def test_wall_detector_merges_duplicates_and_estimates_thickness() -> None:
    analysis = create_analysis(Image.new("RGB", (256, 192), "white"))
    analysis = replace_analysis_lines(
        analysis,
        horizontal=(
            LineCandidate("horizontal", (20, 40), (120, 40)),
            LineCandidate("horizontal", (21, 41), (119, 41)),
            LineCandidate("horizontal", (20, 46), (120, 46)),
            LineCandidate("horizontal", (20, 80), (120, 80)),
        ),
    )

    segments = merge_wall_segments(analysis)
    walls = detect_walls(analysis)

    assert len(segments) == 3
    assert segments[0].support_count == 2
    assert len({wall.id for wall in walls}) == len(walls)
    assert walls[0].metadata[2] == ("estimated_thickness_px", 6)
    assert all(wall.confidence is None for wall in walls)
    assert all(wall.verification_status == "unverified" for wall in walls)


def test_room_detector_finds_rectangular_enclosed_region() -> None:
    records = detect_rooms(create_analysis(create_drawing()))

    assert records
    record = records[0]
    assert record.element_class == "room"
    assert len(record.geometry) >= 4
    assert record.bbox[0] > 0 and record.bbox[1] > 0
    assert dict(record.metadata)["area_px2"] > 0
    assert record.verification_status == "unverified"


def test_room_detector_rejects_incomplete_boundary() -> None:
    records = detect_rooms(create_analysis(create_drawing(open_room=True)))

    assert records == ()


def test_doors_and_windows_reject_an_unadorned_wall_gap() -> None:
    analysis = create_analysis(create_drawing(door_symbol=False))
    analysis = replace_analysis_lines(
        analysis,
        horizontal=(
            LineCandidate("horizontal", (20, 100), (100, 100)),
            LineCandidate("horizontal", (140, 100), (230, 100)),
        ),
    )

    assert detect_doors(analysis) == ()
    assert detect_windows(analysis) == ()


def test_swing_arc_without_a_wall_opening_is_not_a_door() -> None:
    analysis = create_analysis(create_drawing(door_symbol=True))
    analysis = replace_analysis_lines(
        analysis,
        horizontal=(LineCandidate("horizontal", (20, 100), (230, 100)),),
        vertical=analysis.vertical_lines,
    )

    assert detect_doors(analysis) == ()


def test_parallel_frame_lines_without_a_wall_opening_are_not_windows() -> None:
    analysis = create_analysis(create_drawing(window_symbol=True))
    analysis = replace_analysis_lines(
        analysis,
        horizontal=(
            LineCandidate("horizontal", (20, 100), (230, 100)),
            LineCandidate("horizontal", (100, 94), (140, 94)),
            LineCandidate("horizontal", (100, 106), (140, 106)),
        ),
    )

    assert detect_windows(analysis) == ()


def test_window_requires_a_wall_gap_and_bounded_parallel_frames() -> None:
    analysis = create_analysis(create_drawing(window_symbol=True))

    records = detect_windows(analysis)

    assert len(records) == 1
    assert records[0].element_class == "window"
    assert records[0].confidence is None
    assert records[0].verification_status == "unverified"


def test_door_requires_wall_gap_leaf_and_swing_arc() -> None:
    analysis = create_analysis(create_drawing(door_symbol=True))

    records = detect_doors(analysis)

    assert len(records) == 1
    assert records[0].element_class == "door"
    assert dict(records[0].metadata)["swing_arc_found"] is True
    assert dict(records[0].metadata)["leaf_found"] is True
    assert records[0].verification_status == "unverified"


def test_all_detectors_return_common_candidate_records() -> None:
    records = run_all_detectors(create_analysis(create_drawing()))

    assert records
    assert all(record.id for record in records)
    assert all(record.geometry and record.bbox for record in records)
    assert all(record.detection_method for record in records)
    assert all(record.verification_status == "unverified" for record in records)
