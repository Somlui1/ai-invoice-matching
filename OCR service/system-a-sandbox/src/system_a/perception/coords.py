"""Bounding-box maths shared by perception and the report.

Everything that leaves this module is ``[x, y, w, h]``, origin top-left, normalized 0..1 against the
*rendered page after rotation* — the coordinate system declared in ``contracts.COORDINATE_SYSTEM``.
Qwen returns ``bbox_2d = [x1, y1, x2, y2]`` in a mode that varies per model/answer, so the mode is
detected per page (measured rule from the working prototype ``tests/bbox_testv3.py``).
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

BBox = tuple[float, float, float, float]

EMPTY_TEXT = {"", "-", "--", "—", "?", "??", "...", "…", "n/a", "na", "null", "none", "nil", "unknown",
              "unreadable", "illegible", "not readable", "empty", "blank", "not visible", "no text", "[]"}
VISUAL_TYPES = {"signature", "stamp"}
EMPTY_MARKS = {"unsigned", "no signature", "not signed", "no stamp", "empty", "blank", "none"}
MIN_BOX_PX = 4
PARENT_TOLERANCE = 0.01


#: Share of coordinates that may run past 1000 before we stop believing the page answered in 0-1000.
#: A model asked for 0-1000 sometimes lets one stamp box reach 1040; that single outlier must not re-scale
#: every other box on the page (measured on doc 19 page 1: one 1005 value flipped the page to "pixel", every
#: box landed at ~57% of its true height, so each crop re-read sampled blank paper and the fields lost their
#: second reader - which is what actually cost the confidence).
OVER_1000_TOLERANCE = 0.10


def detect_coord_mode(boxes: Sequence[Sequence[float]], img_w: int, img_h: int,
                      forced: str = "auto") -> str:
    """``pixel`` / ``norm1000`` / ``norm1`` - the frame that explains *most* coordinates.

    Decided on the bulk of the coordinates rather than the single largest one, then cross-checked against
    the rendered size: on a page rendered taller than 1000 px, a model that answers in real pixels puts
    most coordinates above 1000, while a model that was asked for 0-1000 overshoots only occasionally.
    """
    if forced and forced != "auto":
        return forced
    vals = [float(v) for b in boxes if b and len(b) == 4 for v in b]
    if not vals:
        return "norm1000"
    mx = max(vals)
    if mx <= 1.0:
        return "norm1"
    over = sum(1 for v in vals if v > 1000) / len(vals)
    if mx <= 1000 or over <= OVER_1000_TOLERANCE:
        return "norm1000" if max(img_w, img_h) > 1100 else "pixel"
    return "pixel"


def xyxy_px(box: Sequence[float], img_w: int, img_h: int, mode: str) -> tuple[float, float, float, float]:
    """Corner box -> pixel rectangle, sorted and clipped to the image."""
    x1, y1, x2, y2 = (float(v) for v in box[:4])
    if mode == "norm1000":
        x1, x2 = x1 * img_w / 1000.0, x2 * img_w / 1000.0
        y1, y2 = y1 * img_h / 1000.0, y2 * img_h / 1000.0
    elif mode == "norm1":
        x1, x2, y1, y2 = x1 * img_w, x2 * img_w, y1 * img_h, y2 * img_h
    x1, x2 = sorted((min(max(x1, 0.0), img_w), min(max(x2, 0.0), img_w)))
    y1, y2 = sorted((min(max(y1, 0.0), img_h), min(max(y2, 0.0), img_h)))
    return x1, y1, x2, y2


def px_to_xywh(rect: Sequence[float], img_w: int, img_h: int) -> BBox:
    """Pixel rectangle -> normalized ``[x, y, w, h]`` (clamped, 4 decimals)."""
    x1, y1, x2, y2 = rect
    w, h = max(img_w, 1), max(img_h, 1)
    x, y = max(0.0, min(1.0, x1 / w)), max(0.0, min(1.0, y1 / h))
    return (round(x, 4), round(y, 4), round(max(0.0, min(1.0 - x, (x2 - x1) / w)), 4),
            round(max(0.0, min(1.0 - y, (y2 - y1) / h)), 4))


def xyxy_to_xywh(box: Sequence[float], img_w: int, img_h: int, mode: str) -> BBox:
    return px_to_xywh(xyxy_px(box, img_w, img_h, mode), img_w, img_h)


def xywh_to_pt(box: Sequence[float], width_pt: float, height_pt: float) -> tuple[float, float, float, float]:
    """Normalized box -> PDF points (x0, y0, x1, y1); used for cropping and for the HTML overlay."""
    x, y, w, h = (float(v) for v in box[:4])
    return (x * width_pt, y * height_pt, (x + w) * width_pt, (y + h) * height_pt)


def text_drop_reason(item: dict) -> str | None:
    """Why an item must not be used (``None`` = keep).  Mirrors the tested prototype rules."""
    b = item.get("bbox_2d")
    if not (isinstance(b, (list, tuple)) and len(b) == 4):
        return "bad_bbox"
    try:
        [float(v) for v in b]
    except (TypeError, ValueError):
        return "bad_bbox"
    t = str(item.get("text") if item.get("text") is not None else "").strip()
    if t.lower().replace(".", "").strip() in EMPTY_TEXT or _is_punct_only(t):
        return "no_text"
    if str(item.get("type")) in VISUAL_TYPES and t.lower() in EMPTY_MARKS:
        return None                              # a blank signature/stamp box stays (E08 needs its bbox)
    return None


def _is_punct_only(t: str) -> bool:
    return bool(t) and not any(ch.isalnum() for ch in t)


def _boxes_on_words(boxes, img_w: int, img_h: int, mode: str, words) -> int:
    """How many model boxes land on top of a printed word under this frame (independent geometry check)."""
    hits = 0
    sample = list(words)[:3000]
    for b in list(boxes)[:200]:
        if not isinstance(b, (list, tuple)) or len(b) != 4:
            continue
        x1, y1, x2, y2 = xyxy_px(b, img_w, img_h, mode)
        for w in sample:
            wx, wy, ww, wh = w["bbox"]
            cx, cy = (wx + ww / 2.0) * img_w, (wy + wh / 2.0) * img_h
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                hits += 1
                break
    return hits


def choose_coord_mode(boxes, img_w: int, img_h: int, words=None, forced: str = "auto") -> str:
    """The coordinate frame that puts the model's boxes **on top of the printed words**.

    Magnitude alone cannot tell a 0-1000 answer from a pixel answer: a page rendered 1240x1754 px can show
    ``bbox_2d=[843, 702]`` as "0-1000" or as "pixels", and guessing wrong shrinks every box on the page in
    one direction, so crops and text-layer comparisons silently stop matching. The PDF text layer knows
    where the words really are, so the frame that lands more boxes on words wins; the magnitude heuristic
    is the fallback for pages with no text layer (scans).
    """
    if forced and forced not in ("auto", "words"):
        return forced
    vals = [float(v) for b in boxes if isinstance(b, (list, tuple)) and len(b) == 4 for v in b]
    if not vals:
        return "norm1000"
    if forced == "auto":
        # bbox_testv3 rule, unchanged: <=1 -> norm1, >1000 -> pixel, else norm1000 on a page rendered >1100 px
        mx = max(vals)
        if mx <= 1.0:
            return "norm1"
        if mx > 1000:
            return "pixel"
        return "norm1000" if max(img_w, img_h) > 1100 else "pixel"
    if max(vals) <= 1.05:
        return "norm1"
    if words:                     # "words": the older text-layer vote, opt-in only
        scores = {m: _boxes_on_words(boxes, img_w, img_h, m, words) for m in ("norm1000", "pixel")}
        if max(scores.values()) > 0:
            return max(("norm1000", "pixel"), key=lambda m: (scores[m], m == "norm1000"))
    return detect_coord_mode(boxes, img_w, img_h, forced)


def filter_items(items: Iterable[dict], img_w: int, img_h: int, forced: str = "auto",
                words: Iterable[dict] | None = None) -> tuple[list, list, str]:
    """Split a model answer into kept items and dropped items (with reason) — never silently discarded."""
    kept_pre, dropped = [], []
    for it in items or []:
        if not isinstance(it, dict):
            dropped.append({"raw_item": str(it)[:120], "drop_reason": "not_an_object"})
            continue
        why = text_drop_reason(it)
        (dropped.append({**it, "drop_reason": why}) if why else kept_pre.append(it))
    mode = choose_coord_mode([it.get("bbox_2d") or [] for it in kept_pre], img_w, img_h, words, forced)
    kept = []
    for it in kept_pre:
        x1, y1, x2, y2 = xyxy_px(it["bbox_2d"], img_w, img_h, mode)
        if x2 - x1 < MIN_BOX_PX or y2 - y1 < MIN_BOX_PX:
            dropped.append({**it, "drop_reason": "zero_area_or_out_of_page"})
            continue
        kept.append({**it, "bbox": px_to_xywh((x1, y1, x2, y2), img_w, img_h)})
    return dedupe(kept), dropped, mode


def dedupe(items: list[dict]) -> list[dict]:
    """Same label + same box twice is a model artefact; keep the first (highest stated confidence)."""
    seen, out = set(), []
    for it in sorted(items, key=lambda i: -float(i.get("confidence") or 0)):
        key = (str(it.get("label") or it.get("type")), str(it.get("text")),
              tuple(round(float(v), 3) for v in it["bbox"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def union_box(boxes: Iterable[Sequence[float]]) -> BBox | None:
    xs = [b for b in boxes if b and len(b) == 4]
    if not xs:
        return None
    x1 = min(float(b[0]) for b in xs)
    y1 = min(float(b[1]) for b in xs)
    x2 = max(float(b[0]) + float(b[2]) for b in xs)
    y2 = max(float(b[1]) + float(b[3]) for b in xs)
    return (round(x1, 4), round(y1, 4), round(max(0.0, x2 - x1), 4), round(max(0.0, y2 - y1), 4))


def inside(child: Sequence[float], parent: Sequence[float], tol: float = PARENT_TOLERANCE) -> bool:
    x, y, w, h = (float(v) for v in child[:4])
    px, py, pw, ph = (float(v) for v in parent[:4])
    return (x >= px - tol and y >= py - tol and x + w <= px + pw + tol and y + h <= py + ph + tol)


def bbox_problems(elements: Iterable[dict]) -> list[dict]:
    """Sanity gate for §Phase 3.4: range, non-empty size, child inside parent (tolerance 0.01)."""
    problems: list[dict] = []
    by_id = {e.get("element_id"): e for e in elements}
    for e in by_id.values():
        b = e.get("bbox")
        if not b:
            continue
        if len(b) != 4 or any(v is None for v in b) or any(not (0.0 <= float(v) <= 1.0) for v in b):
            problems.append({"element_id": e.get("element_id"), "problem": "out_of_range", "bbox": list(b)})
            continue
        if float(b[2]) <= 0 or float(b[3]) <= 0:
            problems.append({"element_id": e.get("element_id"), "problem": "zero_size", "bbox": list(b)})
            continue
        par = by_id.get(e.get("parent_id")) if e.get("parent_id") else None
        if par and par.get("bbox") and not inside(b, par["bbox"]):
            problems.append({"element_id": e.get("element_id"), "problem": "outside_parent",
                             "parent_id": e.get("parent_id"), "bbox": list(b), "parent_bbox": list(par["bbox"])})
    return problems


# ------------------------------------------------------------------ text-layer helpers
def words_in_box(words: Iterable[dict], box: Sequence[float], tol: float = 0.005) -> list[dict]:
    """Text-layer words whose centre falls inside ``box`` (normalized coordinates)."""
    x, y, w, h = (float(v) for v in box[:4])
    out = []
    for wd in words or []:
        bx, by, bw, bh = (float(v) for v in wd["bbox"][:4])
        cx, cy = bx + bw / 2, by + bh / 2
        if x - tol <= cx <= x + w + tol and y - tol <= cy <= y + h + tol:
            out.append(wd)
    return sorted(out, key=lambda d: (round(d["bbox"][1], 3), d["bbox"][0]))


def split_row_cells(words: Sequence[dict], columns: Sequence[tuple[str, Sequence[float]]]) -> dict[str, dict]:
    """Assign row words to table columns by x-overlap, so cells get real text + real boxes.

    ``columns`` is ``[(column_label, normalized_box_of_the_column_header_or_body), ...]``.
    """
    out: dict[str, dict] = {}
    for label, box in columns:
        picked = [w for w in words if overlaps(w["bbox"], box)]
        if not picked:
            continue
        out[label] = {"text": " ".join(str(w["text"]) for w in picked).strip(),
                      "bbox": union_box([w["bbox"] for w in picked]), "words": [w["word_id"] for w in picked]}
    return out


def overlaps(a: Sequence[float], b: Sequence[float], min_overlap: float = 0.2) -> bool:
    ax, ay, aw, ah = (float(v) for v in a[:4])
    bx, by, bw, bh = (float(v) for v in b[:4])
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    area = max(aw * ah, 1e-9)
    return ix * iy / area >= min_overlap


def coord_overflow(items: Iterable[dict], img_w: int, img_h: int, mode: str,
                   tolerance: float = 1.02) -> Optional[dict]:
    """How far the model's coordinates run past the rendered page.

    A model that answers in its own resized pixel grid (not the image we sent) produces boxes outside the
    page; those boxes are dropped by :func:`filter_items`, which without this measurement would look like a
    model that simply did not see the region.  Returned as evidence for the run report, ``None`` when the
    answer fits the page.
    """
    sx = (lambda v: v * img_w / 1000.0) if mode == "norm1000" else \
        (lambda v: v * img_w) if mode == "norm1" else (lambda v: v)
    sy = (lambda v: v * img_h / 1000.0) if mode == "norm1000" else \
        (lambda v: v * img_h) if mode == "norm1" else (lambda v: v)
    max_x = max_y = 0.0
    seen = outside = 0
    for it in items or []:
        box = (it or {}).get("bbox_2d") if isinstance(it, dict) else None
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            x1, y1, x2, y2 = (float(v) for v in box)
        except (TypeError, ValueError):
            continue
        seen += 1
        max_x = max(max_x, sx(x1), sx(x2))
        max_y = max(max_y, sy(y1), sy(y2))
        if sx(x2) > img_w * tolerance or sy(y2) > img_h * tolerance:
            outside += 1
    if not seen or outside == 0:
        return None
    return {"mode": mode, "items_total": seen, "items_outside": outside,
            "max_x_px": round(max_x, 1), "max_y_px": round(max_y, 1), "img_w": img_w, "img_h": img_h,
            "implied_scale_x": round(img_w / max_x, 3) if max_x else None,
            "implied_scale_y": round(img_h / max_y, 3) if max_y else None}
