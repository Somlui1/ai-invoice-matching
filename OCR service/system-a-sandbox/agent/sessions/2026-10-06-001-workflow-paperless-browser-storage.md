# Session Record: 2026-10-06-001-workflow-paperless-browser-storage

- **Timestamp**: `2026-10-06T13:36:00+07:00`
- **Session Goal**: Adjust workflow to connect Paperless documents on the left, PDF preview and process trigger button in the middle, toggleable BBox overlay originating from `system-a`, structured Final/OCR/Validate panels on the right, and store processed cases strictly in the browser.

## Changes Made
1. **Left Panel (Paperless Documents & Browser Stored Cases)**:
   - Added catalog switcher in `web/static/index.html` allowing toggle between Paperless-ngx document list and in-browser case storage.
   - Connected `CaseStore` to document badges so verified cases in the browser display status pills (`AUTO_PASS`, `REVIEW`, `HOLD`, `MANUAL_REVIEW`) and a `💾` indicator.
   - Added UI in `web/static/js/app.js` to list, open, delete, export as JSON, and import JSON for browser-stored cases.
2. **Middle Panel (PDF Display & Processing Controls)**:
   - Integrated center action bar (`#center-action-bar`) directly above the PDF viewer in `web/static/index.html`.
   - Moved primary process trigger button (`#btn-verify`) with mode selection (`production` / `sandbox`, `quick`) into the center panel for immediate access.
   - Maintained live verification steps (1..5) and engine log display in the center stage.
3. **Toggleable BBox Overlay (`src/system_a`)**:
   - Added `toggleMaster()` and `isMasterVisible()` in `web/static/js/bbox-overlay.js`.
   - Added Master Toggle button (`#btn-toggle-bbox`) in viewer navigation bar.
   - Preserved all layer chips (exceptions, header fields, table rows, signatures, words) and bidirectional cross-highlighting.
4. **Right Panel (Final Result + OCR Result + Validate Result)**:
   - Added structured primary view tabs in `web/static/index.html`:
     - 📊 สรุปผล (Final Result)
     - 📝 ผล OCR (OCR Result)
     - ⚖️ ผล Validate (Validation Result)
     - 💻 JSON (Raw Result)
   - Preserved all sub-tabs and DOM IDs (`#tab-rules`, `#tab-exceptions`, `#tab-fields`, `#tab-lines`, `#tab-oracle`, `#tab-json`, `#verdict-card`, `#jsonbox`).
5. **Browser-Only Case Storage**:
   - Implemented `CaseStore` in `web/static/js/app.js` using `localStorage` with quota protection and memory fallback.
   - Verified cases are saved immediately upon verification completion.
   - Reloading a document with an existing browser case loads directly from browser memory without contacting server disk.

## Verification Results
- `python -m pytest web/test_portal.py -q`: 32/32 tests passed (100%).
- `node web/test_ui_logic.mjs .cache/fixture_DMS-20.json`: 27/27 checks passed (100%).
- `node web/test_ui_logic.mjs .cache/fixture_DMS-25.json`: 27/27 checks passed (100%).
- `node web/test_ui_logic.mjs .cache/fixture_DMS-114.json`: 27/27 checks passed (100%).
