# Testing guide

## Run tests

```powershell
python -m pytest -v
python -m compileall -q app.py config.py ingestion processing detection measurement boq visualization verification reports utils tests
python -m pip check
```

To run one area:

```powershell
python -m pytest tests/test_annotation.py -v
python -m pytest tests/test_verification_integration.py -v
python -m pytest tests/test_pdf_export.py tests/test_excel_export.py -v
```

## Test coverage areas

- Valid and corrupted PDFs/images.
- Single/multi-page and blank PDFs.
- Grayscale, threshold, edges, contours and Hough lines.
- Wall merging and room/door/window false-positive guards.
- Calibration units and raster-frame mismatch.
- Horizontal, vertical, diagonal and irregular geometry.
- Duplicate/nested/invalid polygons.
- Review state transitions and audit history.
- Manual confirmation and deletion.
- JSON import/export and malformed JSON.
- Verified/unverified/rejected/manual quantity separation.
- BoQ duplicates, missing rates and cost layers.
- Excel sheet names, formatting and snapshot totals.
- Valid PDF pagination, images and missing-calibration labels.
- Streamlit AppTest reruns and live app health.

## Streamlit verification

Start a temporary local server:

```powershell
python -m streamlit run app.py --server.headless=true --server.address=127.0.0.1 --server.port=8765 --server.enableAgentApi=true
```

Check:

```text
http://127.0.0.1:8765/_stcore/health
```

Stop the server when testing is complete.
