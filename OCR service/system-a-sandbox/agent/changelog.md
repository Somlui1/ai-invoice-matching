# Changelog

All notable permanent changes to System A codebase are documented here.

## [2026-10-06] - Batch Test Automation for Paperless Invoices
### Added
- **Paperless Invoice Batch Test Script (`scripts/test_paperless_invoices.py`)**:
  - Dynamically resolves tag `invoice` (tag ID 5, 98 documents found) in Paperless-ngx API.
  - Sequentially executes System A verification (`process_pdf`) on every document.
  - Saves full Contract 3.0 result JSON for each case (`<out_dir>/DMS-<id>_result.json`).
  - Generates consolidated summary JSON (`<out_dir>/summary.json`) with pass/fail counts, rule breakdown, and case metrics.
  - Supports CLI flags: `--tag`, `--mode production|sandbox`, `--limit`, `--skip-existing`, `--quick`, `--doc-id`, `--out-dir`.
- **Windows Runner Batch Script (`scripts/run_test_invoices.bat`)**: 1-click launcher for batch verification.

## [2026-10-06] - Workflow & UI Portal Redesign
### Added
- **Browser-Only Case Store (`CaseStore`)**: Client-side storage in `localStorage` for verified cases (`web/static/js/app.js`), including listing, opening, deleting, exporting to JSON, and importing from JSON.
- **Master BBox Toggle**: Button in the viewer toolbar (`#btn-toggle-bbox`) allowing operators to toggle all bounding boxes on/off (`web/static/js/bbox-overlay.js`).
- **Middle Action Bar**: Placed prominent "▶ ประมวลผลเอกสาร" (Verify) button, mode selector (`production` / `sandbox`), and quick switch directly in the center panel header above the PDF stage (`web/static/index.html`).
- **Left Panel Catalog Switcher**: Added tabs to switch between "Paperless-ngx" documents and "เคสในเบราว์เซอร์" (Browser Stored Cases), with browser storage badges (`💾`).
- **Structured Right Panel Tabs**: Added primary group tabs for "📊 สรุปผล (Final Result)", "📝 ผล OCR (OCR Result)", "⚖️ ผล Validate (Validation Result)", and "💻 JSON" while maintaining all sub-tabs and DOM IDs for cross-highlighting and automated testing.

### Changed
- `web/static/js/app.js`: Enforced clean pre-process view without BBoxes or auto-loaded historical results upon document selection. BBoxes and results are now rendered exclusively after clicking "▶ ประมวลผลเอกสาร" or when explicitly opening a saved case from the browser cases tab.
- `web/static/index.html`: Restructured layout into left Paperless/Browser case catalog, center PDF preview + prominent verify button + toggleable BBox, and right structured Final/OCR/Validate panels.
- `web/static/styles.css`: Added styles for center action bar, prominent verify button, catalog switcher, browser cases store management, bbox toggle button, and primary result tabs.
- `web/static/js/bbox-overlay.js`: Added `toggleMaster()` and `isMasterVisible()` functions.
- `web/static/js/panels.js`: Added browser storage indicators to catalog items.
