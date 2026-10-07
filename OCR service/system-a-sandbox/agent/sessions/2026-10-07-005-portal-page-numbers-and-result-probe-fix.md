# Session 2026-10-07-005 - Portal: page images 422, `/result` 409 storm, missing recommendation

- **Time**: 2026-10-07T11:50:00+07:00 - 2026-10-07T12:07:00+07:00
- **Type**: Bug fix (`src/test-portal` frontend) + re-verification of the portal against the updated `src/system_a/`
- **Trigger**: the user pasted the live server log of `python -m webapp serve`

## Problem (from the real log)

```
GET /api/documents/15/pages/1/image          200 OK
GET /api/documents/15/result                 409 Conflict
GET /api/documents/19/pages/undefined/image  422 Unprocessable Content
GET /api/documents/19/result                 409 Conflict      (repeat, many times)
GET /api/documents/20/pages/undefined/image  422 Unprocessable Content
```

No bbox overlay could ever appear (the page image itself was never fetched), and the log filled with `409`.

## Root causes

1. `service._public()` sends `"pages": d.page_numbers` — a list of **page numbers** (`[1,2,3]`).
   `pagesHtml()` in `webapp/static/app.js` used each entry as an **object** (`p.page`), so the `<img src>` was
   built from `undefined`.  A document whose `page_numbers` was still empty survived, because the code then fell
   back to `pages_total` - which is why doc 15 worked at first and docs 19/20 did not.
2. `ensureView()` requested `GET …/result` on every repaint without remembering that it had asked, and a document
   with no stored result answers `409` by design (`WEBAPP_PERSIST=false` + a server restart makes this the norm).
3. `applyServer()` read `m.rec`, but the row's key is `recommendation` - so the badge and the `เสร็จ #id · …`
   line had no value.

## Changes

`src/test-portal/webapp/static/app.js` only (no backend, no API change):

- new helper `pageNums(m)`: accepts numbers, `{page:n}` objects or nothing, merges with `pages_total`, deduped and
  sorted; used by the page list (`pagesHtml`) **and** the `หนn` jump links (`docHtml`).
- per-document state gained `probed`: set before the first probe, so a `404`/`409` ends the probing; cleared in
  `applyServer()` when the server reports `done` without a view (fetch the finished result once); set in `forget()`
  after a delete so it does not re-ask.
- `applyServer()` / `watch()` read `m.recommendation` (the key `service._public()` actually sends).

`src/test-portal/tests/test_ui_static.py` +3 tests, each asserting the script against a **live row** of the app:

- `test_page_numbers_are_used_as_the_numbers_the_server_sends` - `/api/documents` rows carry ints, the script
  normalises them, the old `m.pages && m.pages.length` line may not come back, jump links use the same numbers.
- `test_a_document_with_no_stored_result_is_asked_for_only_once` - `probed` exists, blocks re-probing, is cleared
  only by `applyServer` on `done` and set again by `forget`.
- `test_the_state_row_is_read_with_the_keys_the_server_uses` - the row's key is `recommendation`, the script must
  read `m.recommendation` and must not read `m.rec`.

## Verification (real, not simulated)

| Check | Result |
|---|---|
| `node --check webapp/static/app.js` | pass |
| `pytest -q` (src/test-portal) | **112 passed in 6.8 s** (ui_static 7 → 10) |
| old url `…/pages/undefined/image` on a live server | 422 (still correctly rejected) |
| new url `…/pages/1/image`, docs 15 / 19 / 20 | **200** - PNG 3.0 MB / 0.8 MB / 2.3 MB |
| `GET /api/documents/19` | `pages [1,2,3,4]`, `pages_total 4`, key `recommendation` present |
| `GET /api/documents/19/result` while idle | 409 (by design) - now asked once per document |

Same round re-verified the portal against the updated System A (commit `d8000bb` + the 11:31 tree:
`matching.m1_exact_values_item_code`, `evidence.e11_waive_when_values_match`, `oracle.po_list_narrowing`,
`application/receipt_scope.py`, `summary_version` 1.1; JSON schema file unchanged):

- root `pytest -q` **36/36**, `python -m system_a.cli scenarios` **45/45**, portal **112/112**.
- `webapp check` exit 0 and `SYSTEM_A_ENGINE=http webapp check` exit 0 (API in production/litellm).
- **226 real payloads** (`results/paperless_invoices*/DMS-*_result.json`) pass the JSON schema and render through
  `view.build_view`: 21,725 elements → 21,708 boxes, every drawn bbox equals the payload's, refs resolve, rule
  states include `not_evaluated`.
- one live document through the portal on the new code: `done` in 95.3 s, 1155 elements / 1155 boxes, payload
  carries `summary` v1.1, and the verdict moved to `AUTO_PASS` with no exception - a policy change
  (E11 waiver + deterministic M1 pairing), not a portal failure.

## Known gap (not a defect)

The portal still does not render the new top-level `summary` block; the same facts are already shown from
`normalized_fields`, `rule_results`, `evidence` and `oracle_snapshot`.  Also `tests/system_a_stub/config` has no
`evidence:` / `matching:` block yet, so the portal suite exercises the pre-switch policy (System A's own scenarios
S30+ cover the new paths).

## Cleanup

Killed every server started for testing (no listener on 8080/8090), removed `data/`, `.pytest_cache`,
`__pycache__` and all temp scripts; the user's batch output in `results/` was only read, never modified; no token,
supplier name, Tax ID or invoice number is stored in any record.
