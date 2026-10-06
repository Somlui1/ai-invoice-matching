# Session Record: 2026-10-06-002-paperless-clean-view-and-post-process-bbox

- **Timestamp**: `2026-10-06T13:50:00+07:00`
- **Session Goal**: Ensure documents come from Paperless live API (not logs), before process show clean view with zero BBoxes, and after process display result + live BBoxes stored in browser only.

## Key Changes
1. **Enforce Zero BBox Pre-Process**:
   - In `web/static/js/app.js`, updated `selectDoc(d)` to clear all BBox layers (`Overlay.setLayers([])`, `Overlay.render([])`) and display the empty unverified prompt.
   - Removed automatic loading of historical server disk results when selecting a document.
2. **Post-Process Live BBox & Result**:
   - Upon verification completion (`runVerify`), fresh BBox overlay geometry and results are rendered immediately onto the stage and panels.
   - Case is saved strictly in the browser (`CaseStore` via `localStorage`).
3. **Master BBox Toggle**:
   - Added `#btn-toggle-bbox` to allow toggling all BBoxes on/off after processing.
4. **Verification**:
   - `pytest web/test_portal.py -q`: 32/32 tests passed (100%).
   - `node web/test_ui_logic.mjs`: 27/27 checks passed (100%).
   - `python -m webapp check`: connected live to Paperless-ngx.
