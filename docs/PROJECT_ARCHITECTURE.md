# Project architecture

## Processing flow

```text
Upload
  -> ingestion validation
  -> PDF page render or image decode
  -> Phase 3 grayscale/filter/threshold/edges/contours/Hough
  -> Phase 4 rule-based candidate records
  -> Phase 8 review originals and corrected copies
  -> Phase 5 scale and quantities
  -> Phase 6 BoQ and cost
  -> Phase 7 raster annotation
  -> Phase 9 immutable report snapshot
  -> Excel/PDF/PNG export
```

## Module responsibilities

- `ingestion`: file validation, PDF page rendering and image decoding.
- `processing`: OpenCV transformations and PyMuPDF extraction.
- `detection`: walls, rooms, doors and windows as rule-based candidates.
- `measurement`: scale calibration, geometry and quantity dataclasses.
- `verification`: original/corrected records, status transitions and audit data.
- `visualization`: independent raster overlay renderer and PNG encoding.
- `boq`: verified-first records, custom items and catalog/cost operations.
- `reports`: immutable snapshot and format-specific exporters.
- `utils`: shared exceptions and logging.

## Coordinate frames

Image candidate geometry uses source-raster pixels. PDF text/vector metadata uses
PDF page points. PDF page-point coordinates are never passed to measurement
calculations. PDF pages are rendered at 300 DPI for raster analysis.

## State and persistence

Streamlit session state holds active review/calibration state. JSON export/import
provides local review persistence. The project has no database or server-side
authentication.

## Data consistency

Review status determines verified IDs. The quantity calculator receives
corrected review records and verified IDs. BoQ receives the quantity snapshot.
Report exporters receive one `ProjectReportData` object and only format it.
