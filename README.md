# Automated Quantity Takeoff from Architectural Drawings

This is a local training and showcase project for architectural drawing
ingestion, rule-based feature analysis, human verification, quantity
calculation, BoQ estimation and report export.

It does **not** contain a trained YOLO model or an AI drawing detector. Detection
results are geometric candidates produced with PyMuPDF, Pillow and OpenCV.
Candidate records are never automatically promoted to verified elements.

## Features

- PDF page count and 300-DPI page rendering.
- PNG/JPG decoding, dimensions and color metadata.
- Grayscale, Gaussian reduction, adaptive threshold, Canny edges and contours.
- Hough horizontal/vertical line candidates.
- Extracted PDF text, vector paths and embedded-image metadata.
- Conservative wall, room, door and window candidate records.
- Two-point, user-entered scale calibration in metres, centimetres,
  millimetres or feet.
- Pixel length/area calculations and recalculation after geometry corrections.
- Human verify/reject/edit/manual-add/delete review workflow.
- JSON review export/import with audit history.
- INR BoQ records, custom items, waste, contingency, tax and missing-rate warnings.
- Source/annotated raster visualization and annotated PNG export.
- Professional OpenPyXL workbook and multi-page ReportLab PDF export.

## Guided interface

The main interface follows five simple steps:

1. **Upload** — choose an architectural PDF/PNG/JPG drawing.
2. **Scale** — enter two known points and their real distance.
3. **Detect** — find possible walls, rooms, doors and windows.
4. **Review** — verify, reject or correct elements and quantities.
5. **Report** — enter rates and download Excel, PDF or annotated PNG files.

Advanced image settings, audit details, JSON review import/export and cost
catalog editing remain available in expandable sections.

## Architecture

```text
app.py                    Streamlit orchestration and UI
ingestion/                Upload validation, PDF rendering, image decoding
processing/               OpenCV/PyMuPDF analysis
detection/                Rule-based construction-element candidates
measurement/              Scale, geometry and quantity calculations
verification/             Original/corrected review state and audit history
visualization/            Raster overlays and PNG export
boq/                      BoQ generation, rates and cost calculations
reports/                  Immutable snapshot, Excel and PDF exporters
utils/                    Exceptions and logging
tests/                    Pytest unit and integration coverage
docs/                     User, architecture and testing guides
```

Business logic is separate from `app.py`. Export modules consume the shared
immutable `ProjectReportData` snapshot and do not recalculate measurements or
costs.

## Tech stack

- Python 3.12
- Streamlit
- PyMuPDF
- Pillow
- OpenCV
- NumPy
- OpenPyXL
- ReportLab
- Plotly
- Pytest

## Windows installation

Use Windows PowerShell from the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Optional settings:

```text
APP_NAME=Automated Quantity Takeoff
LOG_LEVEL=INFO
```

## Run locally

```powershell
python -m streamlit run app.py
```

Open the URL shown in the terminal, normally `http://localhost:8501`.

## Sample workflow

1. Upload a PDF or PNG/JPG drawing.
2. For PDFs, select a rendered page.
3. Inspect the original, grayscale, threshold, edge and contour views.
4. Review rule-based wall, room, door and window candidates.
5. Apply two-point calibration using coordinates in the source raster.
6. Verify, reject or correct records explicitly.
7. Add manual elements only with confirmation.
8. Enter wall/room/manual quantities, verified record IDs are not inferred.
9. Enter BoQ rates; zero/example rates are not market prices.
10. Configure waste, contingency and tax.
11. Generate reviewed annotation and Excel/PDF exports.

## Testing

Run all tests verbosely:

```powershell
python -m pytest -v
python -m compileall -q app.py config.py ingestion processing detection measurement boq visualization verification reports utils tests
python -m pip check
```

Full documentation:

- [User guide](docs/USER_GUIDE.md)
- [Project architecture](docs/PROJECT_ARCHITECTURE.md)
- [Testing guide](docs/TESTING_GUIDE.md)

## Limitations

- No trained AI or YOLO model.
- Detection is rule-based and may produce false positives or miss elements.
- OCR is not implemented.
- A real-world scale is supplied manually.
- Missing or example rates remain missing/zero; no market prices are invented.
- Human review and approved quantities are required for verified reports.
- PDF points are never silently mixed with raster pixel coordinates.
- JSON review state is local; no database or server authentication is included.

## Set up locally
