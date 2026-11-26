"""Beginner-friendly Streamlit interface for architectural quantity takeoff."""

import hashlib
import logging
from dataclasses import replace

import plotly.express as px
import streamlit as st

from boq.boq_generator import CustomItem, generate_boq
from boq.cost_estimator import calculate_costs
from boq.rate_catalog import RateCatalog, RateCatalogEntry
from config import load_settings
from detection.detector import run_all_detectors
from ingestion.image_loader import load_image
from ingestion.pdf_loader import inspect_pdf, render_pdf_page
from ingestion.validation import validate_drawing
from measurement.quantity_calculator import calculate_quantities
from measurement.scale_calibration import calibrate_scale, validate_calibration_for_raster
from processing.image_preprocessor import analyze_image
from reports.excel_export import export_excel
from reports.pdf_export import export_pdf
from reports.report_data import build_report_snapshot
from utils.exceptions import TakeoffError
from utils.logging_config import configure_logging
from verification.record_editor import create_manual_record, edit_record
from verification.review_manager import ReviewManager
from visualization.annotation import (
    AnnotationOptions,
    create_annotated_drawing,
    export_annotated_png,
)


settings = load_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

STEP_LABELS = ("Upload", "Scale", "Detect", "Review", "Report")


def initialize_state() -> None:
    st.session_state.setdefault("qt_step", 1)
    st.session_state.setdefault("drawing_key", None)
    st.session_state.setdefault("drawing_bytes", None)
    st.session_state.setdefault("drawing_metadata", None)
    st.session_state.setdefault("drawing_name", None)
    st.session_state.setdefault("drawing_extension", None)
    st.session_state.setdefault("pdf_extraction", None)
    st.session_state.setdefault("source_image", None)
    st.session_state.setdefault("image_analysis", None)
    st.session_state.setdefault("candidate_records", ())
    st.session_state.setdefault("review_manager", None)
    st.session_state.setdefault("calibration", None)
    st.session_state.setdefault("quantities", None)
    st.session_state.setdefault("annotation", None)
    st.session_state.setdefault("boq_custom_items", [])
    st.session_state.setdefault("boq_rate_catalog", RateCatalog.default())
    st.session_state.setdefault("include_estimated_boq", False)


def clear_drawing_state() -> None:
    st.session_state["drawing_bytes"] = None
    st.session_state["drawing_metadata"] = None
    st.session_state["drawing_name"] = None
    st.session_state["drawing_extension"] = None
    st.session_state["pdf_extraction"] = None
    st.session_state["source_image"] = None
    st.session_state["image_analysis"] = None
    st.session_state["candidate_records"] = ()
    st.session_state["review_manager"] = None
    st.session_state["calibration"] = None
    st.session_state["quantities"] = None
    st.session_state["annotation"] = None
    st.session_state["quantities"] = None
    st.session_state["annotation"] = None


def is_step_completed(step: int) -> bool:
    if step == 1:
        return st.session_state["drawing_metadata"] is not None
    if step == 2:
        return st.session_state["calibration"] is not None
    if step == 3:
        return bool(st.session_state["candidate_records"]) or (
            st.session_state["image_analysis"] is not None
            and st.session_state["candidate_records"] == ()
        )
    if step == 4:
        return st.session_state["quantities"] is not None
    return False


def render_step_navigation() -> None:
    st.caption("Quantity takeoff progress")
    columns = st.columns(5)
    current = st.session_state["qt_step"]
    for index, (column, label) in enumerate(zip(columns, STEP_LABELS), start=1):
        completed = is_step_completed(index)
        prefix = "✓ " if completed else ""
        state_label = f"{prefix}{index}. {label}"
        button_type = "primary" if index == current else "secondary"
        if column.button(
            state_label,
            width="stretch",
            type=button_type,
            key=f"step_nav_{index}",
        ):
            st.session_state["qt_step"] = index
            st.rerun()


def render_heading(title: str, description: str) -> None:
    st.subheader(title)
    st.write(description)


def render_drawing_preview(
    caption: str = "Your uploaded drawing",
    height_label: str = "Drawing preview",
) -> None:
    source_image = st.session_state["source_image"]
    if source_image is not None:
        st.caption(height_label)
        st.image(
            source_image,
            caption=caption,
            alt="Uploaded architectural drawing",
            width="stretch",
        )


def load_uploaded_drawing(uploaded_file) -> None:
    drawing_bytes = uploaded_file.getvalue()
    drawing_key = hashlib.sha256(
        uploaded_file.name.encode("utf-8") + b":" + drawing_bytes
    ).hexdigest()

    if st.session_state["drawing_key"] != drawing_key:
        clear_drawing_state()
        st.session_state["drawing_key"] = drawing_key
        st.session_state["drawing_bytes"] = drawing_bytes
        st.session_state["drawing_name"] = uploaded_file.name

        try:
            drawing_metadata = validate_drawing(
                uploaded_file.name,
                len(drawing_bytes),
            )
            st.session_state["drawing_metadata"] = drawing_metadata
            st.session_state["drawing_extension"] = drawing_metadata.extension

            if drawing_metadata.extension == "pdf":
                pdf_extraction = inspect_pdf(drawing_bytes)
                st.session_state["pdf_extraction"] = pdf_extraction
                st.session_state["pdf_page"] = 1
                source_image = render_pdf_page(drawing_bytes, 1, dpi=300)
            else:
                loaded_image = load_image(drawing_bytes, uploaded_file.name)
                source_image = loaded_image.image
            st.session_state["source_image"] = source_image
        except TakeoffError as exc:
            logger.warning("Drawing upload failed: %s", exc)
            st.session_state["drawing_key"] = None
            st.session_state["drawing_metadata"] = None
            st.error(str(exc))


def recalculate_quantities() -> None:
    source_image = st.session_state["source_image"]
    review_manager = st.session_state["review_manager"]
    calibration = st.session_state["calibration"]
    if source_image is None or review_manager is None:
        st.session_state["quantities"] = None
        return

    manual_wall = st.session_state.get("manual_wall_m", 0.0)
    manual_room = st.session_state.get("manual_room_m2", 0.0)
    manual_doors = st.session_state.get("manual_door_count", 0)
    manual_windows = st.session_state.get("manual_window_count", 0)
    review = review_manager.snapshot()
    st.session_state["quantities"] = calculate_quantities(
        review.corrected_records(),
        calibration,
        manual_wall_length_m=manual_wall,
        manual_room_area_m2=manual_room,
        manual_door_count=manual_doors,
        manual_window_count=manual_windows,
        verified_record_ids=review.verified_record_ids(),
    )


def get_reviewed_annotation() -> object | None:
    source_image = st.session_state["source_image"]
    review_manager = st.session_state["review_manager"]
    quantities = st.session_state["quantities"]
    calibration = st.session_state["calibration"]
    if source_image is None or review_manager is None:
        return None

    review = review_manager.snapshot()
    reviewed_records = review.corrected_records()
    return create_annotated_drawing(
        source_image,
        reviewed_records,
        quantity_result=quantities,
        calibration=calibration,
        verified_ids=review.verified_record_ids(),
        rejected_ids=tuple(
            record.corrected.id
            for record in review.records
            if record.status == "rejected"
        ),
        manual_ids=tuple(
            record.corrected.id
            for record in review.records
            if record.status == "manual"
        ),
    )


st.set_page_config(
    page_title=settings.app_name,
    page_icon=":material/rule:",
    layout="wide",
)
initialize_state()

st.title("Automated Quantity Takeoff from Architectural Drawings")
st.write(
    "Upload a building floor plan, identify architectural elements, "
    "review measurements, and generate quantity and cost reports in one place."
)

with st.expander("How it works", expanded=False):
    st.write(
        "1. Upload your drawing  •  "
        "2. Set the drawing scale  •  "
        "3. Find building elements  •  "
        "4. Review and confirm quantities  •  "
        "5. Generate your report"
    )

render_step_navigation()
st.divider()

step = st.session_state["qt_step"]

if step == 1:
    render_heading(
        "Start Your Quantity Takeoff",
        "Upload an architectural floor plan to find building elements "
        "and calculate quantities.",
    )
    uploaded_file = st.file_uploader(
        "Choose a drawing",
        type=list(settings.supported_drawing_extensions),
        key="drawing_uploader",
    )
    if uploaded_file is not None:
        try:
            load_uploaded_drawing(uploaded_file)
        except Exception as exc:
            logger.exception("Unexpected drawing upload error")
            st.error(f"Could not open this drawing: {exc}")

    if st.session_state["drawing_metadata"] is not None:
        metadata = st.session_state["drawing_metadata"]
        st.success(f"{st.session_state['drawing_name']} is ready.")
        preview_columns = st.columns([2, 1])
        with preview_columns[0]:
            source_image = st.session_state["source_image"]
            if st.session_state["drawing_extension"] == "pdf":
                pdf_extraction = st.session_state["pdf_extraction"]
                page_number = st.selectbox(
                    "Drawing page",
                    options=range(1, pdf_extraction.page_count + 1),
                    index=st.session_state.get("pdf_page", 1) - 1,
                    key="upload_pdf_page",
                )
                if page_number != st.session_state.get("pdf_page", 1):
                    st.session_state["pdf_page"] = page_number
                    st.session_state["source_image"] = render_pdf_page(
                        st.session_state["drawing_bytes"],
                        page_number,
                        dpi=300,
                    )
                    st.session_state["image_analysis"] = None
                    st.session_state["candidate_records"] = ()
                    st.session_state["review_manager"] = None
                    st.session_state["quantities"] = None
                    st.session_state["calibration"] = None
                    st.session_state["review_manager"] = None
                    source_image = st.session_state["source_image"]
            st.image(
                source_image,
                caption=f"{st.session_state['drawing_name']} — drawing preview",
                alt="Uploaded architectural floor plan",
                width="stretch",
            )
        with preview_columns[1]:
            st.markdown("### Drawing details")
            st.text(f"File: {st.session_state['drawing_name']}")
            st.text(f"Size: {metadata.size_bytes:,} bytes")
            if st.session_state["source_image"] is not None:
                width, height = st.session_state["source_image"].size
                st.text(f"Resolution: {width} x {height} pixels")
            if st.session_state["drawing_extension"] == "pdf":
                st.text(
                    f"Pages: {st.session_state['pdf_extraction'].page_count}"
                )
        if st.button(
            "Continue to Scale",
            type="primary",
            width="stretch",
            key="continue_scale",
        ):
            st.session_state["qt_step"] = 2
            st.rerun()

elif step == 2:
    render_heading(
        "Set Your Drawing Scale",
        "Tell the application the real-world distance represented by "
        "a known distance on your drawing.",
    )
    if st.session_state["source_image"] is None:
        st.warning("Upload a drawing before setting the scale.")
        if st.button("Back to Upload", type="primary", key="scale_back_upload"):
            st.session_state["qt_step"] = 1
            st.rerun()
    else:
        columns = st.columns([2, 1])
        with columns[0]:
            render_drawing_preview(
                "Preview for calibration",
                "Drawing preview",
            )
        with columns[1]:
            st.markdown("### Known distance")
            st.write(
                "Enter the pixel positions of two points that you know belong "
                "to a real distance. The distance must be measured on this drawing."
            )
            st.markdown("**Point 1**")
            x1 = st.number_input(
                "Point 1 — horizontal position",
                min_value=0.0,
                max_value=float(st.session_state["source_image"].width),
                value=0.0,
                key="scale_x1",
            )
            y1 = st.number_input(
                "Point 1 — vertical position",
                min_value=0.0,
                max_value=float(st.session_state["source_image"].height),
                value=0.0,
                key="scale_y1",
            )
            st.markdown("**Point 2**")
            x2 = st.number_input(
                "Point 2 — horizontal position",
                min_value=0.0,
                max_value=float(st.session_state["source_image"].width),
                value=float(st.session_state["source_image"].width),
                key="scale_x2",
            )
            y2 = st.number_input(
                "Point 2 — vertical position",
                min_value=0.0,
                max_value=float(st.session_state["source_image"].height),
                value=0.0,
                key="scale_y2",
            )
            distance = st.number_input(
                "Real distance",
                min_value=0.0,
                value=1.0,
                step=0.1,
                key="scale_distance",
            )
            unit = st.selectbox(
                "Distance unit",
                ("m", "cm", "mm", "ft"),
                key="scale_unit",
            )
            if st.button(
                "Set Drawing Scale",
                type="primary",
                width="stretch",
                key="apply_scale",
            ):
                try:
                    calibration = calibrate_scale(
                        x1,
                        y1,
                        x2,
                        y2,
                        distance,
                        unit,
                        source_width=st.session_state["source_image"].width,
                        source_height=st.session_state["source_image"].height,
                        coordinate_frame="source image pixels; origin at top-left",
                    )
                    st.session_state["calibration"] = calibration
                    st.session_state["quantities"] = None
                    st.success("Drawing scale set.")
                except TakeoffError as exc:
                    st.error(str(exc))

        calibration = st.session_state["calibration"]
        if calibration is not None:
            validate_calibration_for_raster(
                calibration,
                source_width=st.session_state["source_image"].width,
                source_height=st.session_state["source_image"].height,
                coordinate_frame="source image pixels; origin at top-left",
            )
            st.success(
                f"Scale ready: {calibration.pixels_per_metre:.2f} drawing pixels "
                f"represent one metre."
            )
        if st.button(
            "Continue to Detect",
            type="primary",
            width="stretch",
            key="continue_detect",
        ):
            st.session_state["qt_step"] = 3
            st.rerun()

elif step == 3:
    render_heading(
        "Find Building Elements",
        "The application will examine your drawing and identify possible "
        "walls, doors, windows, and rooms.",
    )
    if st.session_state["source_image"] is None:
        st.warning("Upload a drawing first.")
    else:
        preview, action = st.columns([2, 1])
        with preview:
            render_drawing_preview(
                "Drawing ready for element finding",
                "Drawing preview",
            )
        with action:
            st.markdown("### Automatic finding")
            st.write(
                "This uses rule-based drawing patterns. The results are "
                "possible elements and must be reviewed."
            )
            if st.button(
                "Detect Elements",
                type="primary",
                width="stretch",
                key="detect_elements",
            ):
                with st.status("Finding possible building elements...", expanded=True) as status:
                    try:
                        image_analysis = analyze_image(
                            st.session_state["source_image"]
                        )
                        candidate_records = run_all_detectors(image_analysis)
                        st.session_state["image_analysis"] = image_analysis
                        st.session_state["candidate_records"] = candidate_records
                        review_manager = ReviewManager(
                            candidate_records,
                            source_width=st.session_state["source_image"].width,
                            source_height=st.session_state["source_image"].height,
                        )
                        st.session_state["review_manager"] = review_manager
                        st.session_state["quantities"] = None
                        status.update(
                            label="Element finding complete",
                            state="complete",
                        )
                    except (TakeoffError, ValueError) as exc:
                        status.update(
                            label="Element finding could not finish",
                            state="error",
                        )
                        st.error(str(exc))

            with st.expander("Advanced settings"):
                st.write(
                    "Automatic detection settings are fixed for this local showcase "
                    "to keep the tool simple and predictable."
                )

        candidate_records = st.session_state["candidate_records"]
        if st.session_state["image_analysis"] is not None:
            st.markdown("### Detection summary")
            counts = {
                "wall": sum(
                    1 for record in candidate_records
                    if record.element_class == "wall"
                ),
                "door": sum(
                    1 for record in candidate_records
                    if record.element_class == "door"
                ),
                "window": sum(
                    1 for record in candidate_records
                    if record.element_class == "window"
                ),
                "room": sum(
                    1 for record in candidate_records
                    if record.element_class == "room"
                ),
            }
            columns = st.columns(4)
            for column, (label, count) in zip(
                columns,
                (
                    ("Walls", counts["wall"]),
                    ("Doors", counts["door"]),
                    ("Windows", counts["window"]),
                    ("Rooms", counts["room"]),
                ),
            ):
                column.metric(label, count, border=True)
            st.warning(
                "These are automatic detection results. Review them before "
                "using them in a report."
            )
            if st.button(
                "Continue to Review",
                type="primary",
                width="stretch",
                key="continue_review",
            ):
                st.session_state["qt_step"] = 4
                st.rerun()

elif step == 4:
    render_heading(
        "Review Your Results",
        "Check the detected elements and confirm which measurements are correct.",
    )
    source_image = st.session_state["source_image"]
    review_manager = st.session_state["review_manager"]
    if source_image is None or review_manager is None:
        st.warning("Detect building elements before reviewing.")
    else:
        recalculate_quantities()
        quantities = st.session_state["quantities"]
        review_snapshot = review_manager.snapshot()
        annotation = get_reviewed_annotation()

        left, right = st.columns([3, 2])
        with left:
            st.markdown("### Drawing")
            if annotation is not None:
                st.image(
                    annotation.image,
                    caption="Drawing with review status",
                    alt="Annotated architectural drawing",
                    width="stretch",
                )
        with right:
            st.markdown("### Detected elements")
            records = review_snapshot.records
            if not records:
                st.info("No possible elements were found.")
            else:
                status_filter = st.segmented_control(
                    "Show",
                    options=("All", "Needs Review", "Verified", "Rejected"),
                    default="All",
                    key="review_status_simple",
                )
                filtered = []
                for record in records:
                    display_status = {
                        "unverified": "Needs Review",
                        "verified": "Verified",
                        "rejected": "Rejected",
                        "manual": "Verified",
                    }[record.status]
                    if status_filter == "All" or display_status == status_filter:
                        filtered.append(record)

                if filtered:
                    selected_id = st.selectbox(
                        "Element",
                        options=tuple(record.corrected.id for record in filtered),
                        key="review_selected_element",
                    )
                    selected = active_record = next(
                        record
                        for record in filtered
                        if record.corrected.id == selected_id
                    )
                    status_label = {
                        "unverified": "Needs Review",
                        "verified": "Verified",
                        "rejected": "Rejected",
                        "manual": "Verified",
                    }[selected.status]
                    st.markdown(
                        f"**{selected.corrected.element_class.title()}**  "
                        f"`{status_label}`"
                    )
                    st.text(f"Element ID: {selected.corrected.id}")
                    if selected.corrected.element_class == "wall":
                        wall = next(
                            (
                                item
                                for item in quantities.walls
                                if item.id == selected.corrected.id
                            ),
                            None,
                        )
                        if wall is not None:
                            if wall.length_m is not None:
                                st.metric(
                                    "Length",
                                    f"{wall.length_m:.3f} m",
                                    border=True,
                                )
                            else:
                                st.metric(
                                    "Length",
                                    f"{wall.length_px:.1f} px",
                                    border=True,
                                )
                    if selected.corrected.element_class == "room":
                        room = next(
                            (
                                item
                                for item in quantities.rooms
                                if item.id == selected.corrected.id
                            ),
                            None,
                        )
                        if room is not None:
                            if room.area_m2 is not None:
                                st.metric(
                                    "Area",
                                    f"{room.area_m2:.3f} m²",
                                    border=True,
                                )
                            else:
                                st.metric(
                                    "Area",
                                    f"{room.area_px2:.1f} px²",
                                    border=True,
                                )

                    action_columns = st.columns(3)
                    if action_columns[0].button(
                        "Verify",
                        width="stretch",
                        key="simple_verify",
                        type="primary",
                    ):
                        review_manager.set_status(
                            selected_id,
                            "verified",
                        )
                        recalculate_quantities()
                        st.rerun()
                    if action_columns[1].button(
                        "Reject",
                        width="stretch",
                        key="simple_reject",
                    ):
                        review_manager.set_status(
                            selected_id,
                            "rejected",
                        )
                        recalculate_quantities()
                        st.rerun()

                    with st.expander("Edit this element"):
                        edited_class = st.selectbox(
                            "Element type",
                            ("wall", "room", "door", "window"),
                            index=("wall", "room", "door", "window").index(
                                selected.corrected.element_class
                            ),
                            key="simple_edit_class",
                        )
                        geometry_text = st.text_area(
                            "Positions as x,y pairs",
                            value="; ".join(
                                f"{point[0]},{point[1]}"
                                for point in selected.corrected.geometry
                            ),
                            key="simple_edit_geometry",
                        )
                        note = st.text_input(
                            "Correction note",
                            value=selected.correction_note,
                            key="simple_edit_note",
                        )
                        if st.button(
                            "Save Correction",
                            width="stretch",
                            key="simple_save_edit",
                        ):
                            try:
                                parsed_geometry = tuple(
                                    (
                                        float(pair.split(",")[0].strip()),
                                        float(pair.split(",")[1].strip()),
                                    )
                                    for pair in geometry_text.split(";")
                                    if pair.strip()
                                )
                                bbox = selected.corrected.bbox
                                if edited_class in {"door", "window"}:
                                    xs = [point[0] for point in parsed_geometry]
                                    ys = [point[1] for point in parsed_geometry]
                                    if xs and ys:
                                        bbox = (min(xs), min(ys), max(xs), max(ys))
                                corrected = edit_record(
                                    selected.corrected,
                                    element_class=edited_class,
                                    geometry=parsed_geometry,
                                    bbox=bbox,
                                    source_width=source_image.width,
                                    source_height=source_image.height,
                                )
                                review_manager.edit_record(
                                    selected_id,
                                    corrected,
                                    note=note,
                                )
                                recalculate_quantities()
                                st.success("Correction saved.")
                                st.rerun()
                            except (IndexError, ValueError, TakeoffError) as exc:
                                st.error(str(exc))

                with st.expander("Add a missing element"):
                    manual_id = st.text_input(
                        "Element ID",
                        value="",
                        key="simple_manual_id",
                    )
                    manual_class = st.selectbox(
                        "Element type",
                        ("wall", "room", "door", "window"),
                        key="simple_manual_class",
                    )
                    manual_geometry = st.text_area(
                        "Positions as x,y pairs",
                        key="simple_manual_geometry",
                        placeholder="10,20; 50,20",
                    )
                    manual_confirmed = st.checkbox(
                        "I confirm this element is correct",
                        key="simple_manual_confirmed",
                    )
                    if st.button(
                        "Add Element",
                        width="stretch",
                        key="simple_add_manual",
                    ):
                        try:
                            parsed_geometry = tuple(
                                (
                                    float(pair.split(",")[0].strip()),
                                    float(pair.split(",")[1].strip()),
                                )
                                for pair in manual_geometry.split(";")
                                if pair.strip()
                            )
                            manual_record = create_manual_record(
                                manual_id,
                                manual_class,
                                parsed_geometry,
                                source_width=source_image.width,
                                source_height=source_image.height,
                            )
                            review_manager.add_manual_record(
                                manual_record,
                                note="Manually added",
                                explicitly_confirmed=manual_confirmed,
                            )
                            recalculate_quantities()
                            st.success("Element added.")
                            st.rerun()
                        except (IndexError, ValueError, TakeoffError) as exc:
                            st.error(str(exc))

        if quantities is not None:
            st.markdown("### Verified quantity summary")
            summary = quantities.summary
            columns = st.columns(4)
            columns[0].metric(
                "Wall length",
                f"{summary.verified_wall_length_m:.3f} m",
                border=True,
            )
            columns[1].metric(
                "Room area",
                f"{summary.floor_area_m2:.3f} m²",
                border=True,
            )
            columns[2].metric(
                "Doors",
                str(summary.verified_door_count),
                border=True,
            )
            columns[3].metric(
                "Windows",
                str(summary.verified_window_count),
                border=True,
            )
            if summary.unverified_wall_count:
                st.caption(
                    f"{summary.unverified_wall_count} wall candidate(s) still need review."
                )

        with st.expander("Advanced review details"):
            review_snapshot = review_manager.snapshot()
            st.json(
                {
                    "statistics": review_snapshot.statistics(),
                    "audit_events": [
                        {
                            "record_id": event.record_id,
                            "action": event.action,
                            "before": event.before_status,
                            "after": event.after_status,
                        }
                        for event in review_snapshot.audit_history
                    ],
                }
            )
            st.download_button(
                "Export review JSON",
                data=review_manager.snapshot().to_json(),
                file_name="drawing_review.json",
                mime="application/json",
                icon=":material/download:",
            )
            review_import = st.file_uploader(
                "Import review JSON",
                type=["json"],
                key="simple_review_import",
            )
            if review_import is not None:
                try:
                    imported_manager = ReviewManager.from_json(
                        review_import.getvalue().decode("utf-8")
                    )
                    st.session_state[
                        f"review:{st.session_state['drawing_name']}:"
                        f"{st.session_state['drawing_metadata'].size_bytes}:"
                        f"{source_image.width}x{source_image.height}"
                    ] = imported_manager
                    st.success("Review corrections imported.")
                    st.rerun()
                except (UnicodeDecodeError, TakeoffError) as exc:
                    st.error(str(exc))

        if st.button(
            "Continue to Report",
            type="primary",
            width="stretch",
            key="continue_report",
        ):
            st.session_state["qt_step"] = 5
            st.rerun()

elif step == 5:
    render_heading(
        "Your Quantity Takeoff Report",
        "Generate and download a report containing your verified measurements "
        "and estimated costs.",
    )
    source_image = st.session_state["source_image"]
    review_manager = st.session_state["review_manager"]
    quantities = st.session_state["quantities"]
    if source_image is None or review_manager is None or quantities is None:
        st.warning("Complete the review step before generating a report.")
    else:
        summary = quantities.summary
        cards = st.columns(5)
        cards[0].metric(
            "Verified wall length",
            f"{summary.verified_wall_length_m:.3f} m",
            border=True,
        )
        cards[1].metric(
            "Verified room area",
            f"{summary.floor_area_m2:.3f} m²",
            border=True,
        )
        cards[2].metric("Doors", str(summary.verified_door_count), border=True)
        cards[3].metric("Windows", str(summary.verified_window_count), border=True)

        with st.expander("Cost settings"):
            st.write(
                "Estimated costs depend on rates entered by the user. "
                "The starting catalog contains example rows with zero rates."
            )
            catalog = st.session_state["boq_rate_catalog"]
            catalog_rows = [
                {
                    "item_id": entry.item_id,
                    "name": entry.name,
                    "unit": entry.unit,
                    "rate_INR": entry.rate,
                    "source": entry.source,
                }
                for entry in catalog.entries()
            ]
            if catalog_rows:
                catalog_editor = st.data_editor(
                    catalog_rows,
                    num_rows="dynamic",
                    hide_index=True,
                    key="simple_cost_catalog",
                    alt="Editable cost rate catalog",
                )
                if st.button(
                    "Save Cost Rates",
                    width="stretch",
                    key="save_simple_rates",
                ):
                    try:
                        updated_catalog = RateCatalog()
                        for row in catalog_editor:
                            updated_catalog.upsert(
                                RateCatalogEntry(
                                    item_id=str(row["item_id"]),
                                    name=str(row["name"]),
                                    unit=str(row["unit"]),
                                    rate=float(row["rate_INR"]),
                                    currency="INR",
                                    source=str(row["source"]),
                                )
                            )
                        st.session_state["boq_rate_catalog"] = updated_catalog
                        st.success("Cost rates saved.")
                        st.rerun()
                    except (KeyError, TypeError, ValueError, TakeoffError) as exc:
                        st.error(str(exc))
            st.download_button(
                "Download Rate Catalog",
                data=catalog.to_csv(),
                file_name="quantity_takeoff_rates.csv",
                mime="text/csv",
            )
            catalog_upload = st.file_uploader(
                "Import Rate Catalog CSV",
                type=["csv"],
                key="simple_rate_import",
            )
            if catalog_upload is not None:
                try:
                    imported_catalog = RateCatalog.from_csv_text(
                        catalog_upload.getvalue().decode("utf-8")
                    )
                    st.session_state["boq_rate_catalog"] = imported_catalog
                    st.success("Rate catalog imported.")
                    st.rerun()
                except (UnicodeDecodeError, TakeoffError) as exc:
                    st.error(str(exc))

            with st.expander("Add a custom cost item"):
                custom_id = st.text_input(
                    "Custom item ID",
                    key="simple_custom_id",
                )
                custom_name = st.text_input(
                    "Custom item name",
                    key="simple_custom_name",
                )
                custom_quantity = st.number_input(
                    "Custom quantity",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="simple_custom_quantity",
                )
                custom_unit = st.text_input(
                    "Custom unit",
                    value="nos",
                    key="simple_custom_unit",
                )
                custom_rate = st.number_input(
                    "Custom rate (INR)",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    key="simple_custom_rate",
                )
                if st.button(
                    "Add custom item",
                    width="stretch",
                    key="simple_add_custom",
                ):
                    try:
                        custom_item = CustomItem(
                            item_id=custom_id,
                            name=custom_name,
                            description="Manually added cost item",
                            quantity=custom_quantity,
                            unit=custom_unit,
                            rate=custom_rate,
                            status="manual",
                            rate_source="user-entered",
                        )
                        st.session_state["boq_custom_items"].append(custom_item)
                        st.success("Custom cost item added.")
                        st.rerun()
                    except TakeoffError as exc:
                        st.error(str(exc))

            waste = st.number_input(
                "Waste (%)",
                min_value=0.0,
                value=0.0,
                step=0.5,
                key="simple_waste",
            )
            contingency = st.number_input(
                "Contingency (%)",
                min_value=0.0,
                value=0.0,
                step=0.5,
                key="simple_contingency",
            )
            tax = st.number_input(
                "Tax (%)",
                min_value=0.0,
                value=0.0,
                step=0.5,
                key="simple_tax",
            )

        catalog = st.session_state["boq_rate_catalog"]
        waste = st.session_state.get("simple_waste", 0.0)
        contingency = st.session_state.get("simple_contingency", 0.0)
        tax = st.session_state.get("simple_tax", 0.0)

        include_estimated = st.toggle(
            "Include estimated items separately",
            value=False,
            key="simple_include_estimated",
        )
        try:
            boq_items = generate_boq(
                quantities,
                custom_items=tuple(
                    st.session_state["boq_custom_items"]
                ),
                include_estimated=include_estimated,
                currency="INR",
            )
        except TakeoffError as exc:
            st.error(str(exc))
            boq_items = ()

        priced_items = []
        for item in boq_items:
            if item.status == "manual":
                rate = item.rate
                rate_source = item.rate_source
            else:
                catalog_entry = catalog.get(
                    "wall"
                    if item.name.startswith("Wall")
                    else "floor"
                    if item.name.startswith("Floor")
                    else "door"
                    if item.name.startswith("Door")
                    else "window"
                    if item.name.startswith("Window")
                    else item.item_id
                )
                if catalog_entry is None:
                    catalog_entry = catalog.get(item.item_id)
                rate = catalog_entry.rate if catalog_entry is not None else item.rate
                rate_source = (
                    catalog_entry.source
                    if catalog_entry is not None
                    else item.rate_source
                )
            priced_items.append(
                replace(
                    item,
                    rate=rate,
                    total=item.quantity * rate,
                    rate_source=rate_source if rate > 0 else "missing",
                )
            )

        try:
            cost = calculate_costs(
                tuple(priced_items),
                waste_percent=waste,
                contingency_percent=contingency,
                tax_percent=tax,
                currency="INR",
                allow_missing_rates=True,
            )
        except TakeoffError as exc:
            st.error(str(exc))
            cost = None

        if cost is not None:
            cards[4].metric(
                "Estimated total",
                f"₹{cost.grand_total:,.2f}",
                border=True,
            )
            if cost.missing_rate_item_ids:
                st.warning(
                    "Some items have missing or zero rates. "
                    "Enter rates before using the estimated total."
                )
            if cost.grand_total == 0:
                st.caption(
                    "The estimated total is ₹0 because no usable rates have been entered."
                )

        annotation = get_reviewed_annotation()
        if annotation is not None:
            st.markdown("### Final preview")
            st.image(
                annotation.image,
                caption="Your annotated drawing",
                alt="Annotated architectural drawing",
                width="stretch",
            )

        st.markdown("### Download your report")
        if annotation is None:
            st.error("The annotated drawing is not ready.")
        else:
            if cost is not None:
                try:
                    snapshot = build_report_snapshot(
                        project_name=settings.app_name,
                        filename=st.session_state["drawing_name"],
                        file_size_bytes=st.session_state["drawing_metadata"].size_bytes,
                        source_image=st.session_state["source_image"],
                        annotated_image=annotation.image,
                        quantities=quantities,
                        review=review_manager.snapshot(),
                        boq_items=tuple(priced_items),
                        cost=cost,
                        calibration=st.session_state["calibration"],
                        source_width=st.session_state["source_image"].width,
                        source_height=st.session_state["source_image"].height,
                        coordinate_frame="source image pixels; origin at top-left",
                    )
                    excel_bytes = export_excel(snapshot)
                    pdf_bytes = export_pdf(snapshot)
                    download_columns = st.columns(3)
                    download_columns[0].download_button(
                        "Download Excel Report",
                        data=excel_bytes,
                        file_name="quantity_takeoff_report.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch",
                    )
                    download_columns[1].download_button(
                        "Download PDF Report",
                        data=pdf_bytes,
                        file_name="quantity_takeoff_report.pdf",
                        mime="application/pdf",
                        width="stretch",
                    )
                    download_columns[2].download_button(
                        "Download Annotated Drawing",
                        data=export_annotated_png(annotation),
                        file_name="annotated_drawing.png",
                        mime="image/png",
                        width="stretch",
                    )
                except (TakeoffError, ValueError) as exc:
                    st.error(f"Report is not ready: {exc}")
            else:
                st.warning("Enter or confirm cost settings before downloading.")
