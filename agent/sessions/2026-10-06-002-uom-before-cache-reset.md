# Session 2026-10-06-002 — วัดราคาของงาน UOM ก่อนจ่าย perception cache reset

- Date: 2026-10-06
- Time: 08:16–08:32 (+07:00)
- Status: **measurement only — engine code not touched, VLM calls 0**
- User direction for this round: option 1 = "ทำ UOM + `fitz`→`pymupdf` ในรอบเดียว แล้ว re-pin baseline"

## Why a measurement round

แก้ perception 1 บรรทัด = ทิ้ง cache ทั้งก้อน (112 extractions, 425 หน้า, ≈3 ชม. VLM) ตามที่
DEC-013/DEC-016 ตกลงกันไว้ งานที่แพงขนาดนั้นต้องพิสูจน์สมมติฐานก่อนด้วยของที่ถูก (cache เดิมเก็บ
`raw` + `word_ids` + `region` ต่อ cell ครบ) ไม่ใช่จ่ายแล้วค่อยรู้ว่าสมมติฐานผิด

## What was measured (all free)

**1) The premise was wrong.** `.agent/harness/uom_probe.py` over the baseline cache: 608 lines →
UOM dual-read **202**, single-reader **168**, absent **238**. Of the 238, **236 sit on pages that print
no per-row unit column at all** (verified on the paper: DMS-40's headers are
NO./รหัสสินค้า/รายการ/จำนวน/**หน่วยละ**/ส่วนลด/จำนวนเงิน — "หน่วยละ" is *unit price*, and `หน่วย` alone also
opens "หน่วยเงิน" = currency). Forcing the model to emit a UOM column there would **invent a value that is
not printed on the document**, which OQ-09 forbids and which would then be trusted downstream.

**2) Where the unit does exist, it is in the column caption** (DMS-65: "จำนวนแผ่น Pcs.",
"นน./แผ่น Kgs./Sheet" over the quantity columns). Restricted to the geometry a real implementation could
use (the caption strip above the first row, within that column's x-band, strict unit vocabulary), only
**12 of 143** measured absent cells are recoverable that way, in **2 documents**.

**3) A comparison-policy ceiling.** `.agent/harness/consensus_probe.py` replays 1,621 baseline items the
engine called single-reader, then replays V-01's real policy (required fields/cells, per-group
`min` + `require_agreement` from `config/standards/v6.6/policy.yaml`) per document:

| policy | documents passing V-01 |
|---|---|
| P0 today | **0 / 99** |
| P1 also accept a contiguous word run inside the cell box (+ small pad) | 1 / 99 |
| P2 + token containment | 3 / 99 |
| P3 + value present in the printed row | 5 / 99 |
| P4 + value present anywhere on the page *(not defensible evidence)* | 16 / 99 |

**4) The price of solving UOM perfectly** (`--assume-uom-solved`): P0 **0/99**, P2 **11/99**, P3 **13/99**.
So UOM is *not* the biggest wall. With UOM solved, the blockers are:

- `field.customer_name` readers disagree — **43 docs**: the VLM merges the caption into the value
  ("ขายให้แก่ SOLD TO บริษัท อาปิโก ไฮเทค พาร์ทส์ จำกัด") while the text layer is glyph-mangled Thai
  ("บ ริ ษั ท อ า ป บ โก") — marks are folded already, consonant misreads are not fixable by folding.
- money/qty cells where the printed number is **on the page but not inside the box the model claimed**
  (`page_substring` 34–39 docs) — a grounding defect, not a reading defect.
- cells the model never returned: qty 15 / unit_price 16 / amount 12 docs.
- box growth alone is weak: pad 0.008→0.05 moves 103→188 line cells into "would agree" but changes
  **no document's verdict**.

**5) A cache defect found on the way**: `max_words = 2500` is per document, so late pages of long
documents store **zero** words (DMS-40 p5: 2,054 text-layer characters, 0 stored words). 42/99 documents
lose words; **84 required cells sit on pages whose words were cut**.

**6) A control-plane fact**: `.agent/` is gitignored (root `.gitignore:212`) and `git ls-files` returns
**0 files** — baseline copies, `todo.md`, `decisions.md`, `recovery.md` exist only on this disk. That is
why recovery.md speaks of "copy back" rather than "git restore", and it is a single-copy risk for the
baseline DEC-015 depends on.

## Decision taken

Do **not** run the "force the UOM column" perception round. The bundle worth one cache reset is:

1. prompt: field values must not swallow their own caption (attacks the 43-doc `customer_name` wall —
   an extraction-quality bug, not a policy relaxation);
2. prompt: report the unit **printed in the caption of the quantity column**, with the caption text+bbox
   as provenance, and `NO_UOM_PRINTED` when the document prints none (honest `null_reason` instead of a
   generic "อ่านไม่ผ่าน");
3. code: accept a contiguous word run inside the cell box (+ pad ≈0.02) — 145 line cells + 14 fields at
   pad 0.02, deterministic, no guessing;
4. code: `max_words` cap must not delete a page's words from `consensus_units`;
5. `import fitz` → `import pymupdf` in the same commit (DEC-016 pays the reset once);
6. re-pin baseline. **Honest expected ceiling: V-01 ≈ 11–13 / 99, not 99** — AUTO_PASS stays gated by
   V-05/BLOCKER-01 (Table 4 rows) regardless.

Escalations for humans (not engine work): whether V-01 may accept a caption-derived unit, and whether it
should still block when a document prints no unit anywhere (45 docs blocked today).

## Files

- Added `.agent/harness/uom_probe.py`, `.agent/harness/consensus_probe.py`,
  `.agent/eval/uom_probe_r0.json`, `.agent/eval/consensus_probe_r0.json`,
  `.agent/eval/probe_DMS-40_p1.png`, `.agent/eval/probe_DMS-65_p1.png` (all under gitignored `.agent/`)
- No change under `system-a/`
