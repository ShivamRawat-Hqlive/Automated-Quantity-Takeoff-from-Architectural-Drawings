# User guide

## 1. Upload a drawing

Upload a PDF or PNG/JPG. Corrupted and mismatched files are rejected. PDF
uploads expose a page selector. PNG/JPG uploads expose source dimensions and
color metadata.

## 2. Review the analysis

The app exposes original, grayscale, Gaussian-smoothed, binary threshold,
Canny edge, contour and Hough line views. These are geometric analysis outputs,
not verified construction elements.

## 3. Review elements

Open **Review and verify**. Search by ID, class or note and filter by status.
Verify or reject a record explicitly. Edit only points or bounding boxes inside
the source raster. Add manual elements only after confirmation.

Original detector values remain visible separately. Corrected values and audit
events are preserved.

## 4. Calibrate

Enter two points in the displayed source raster and the real distance between
them. Select metres, centimetres, millimetres or feet. Recalibration replaces
the current calibration for the same drawing only.

## 5. Review quantities

Verified and manual records contribute to verified quantities. Unverified and
rejected records stay separate. Rejected records are excluded. Geometry edits
recalculate lengths and areas through Phase 5.

## 6. Create BoQ and costs

The default BoQ starts from verified quantities. Enable estimated quantities
only when they are intentionally needed as separate rows.

Import or edit a rate catalog. The default INR rows are labeled examples and
have zero rates. Enter user rates; zero/missing rates are never presented as
market prices.

Waste is applied to the subtotal, contingency to subtotal plus waste, and tax
to subtotal plus waste and contingency.

## 7. Export

Download the original/annotated PNG, Excel workbook or PDF report. Excel and PDF
use the same report snapshot. Missing calibration or rates are included in
warnings and report limitations.
