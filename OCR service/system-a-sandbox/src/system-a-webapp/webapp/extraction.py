"""Replay perception: the OCR items of a batch report -> ``aiva.extraction/2.0`` (the System A input contract).

Why this exists.  ``report.html`` holds what the OCR engine already read (type / label / text / bbox per item).
Re-using it lets the validation half of System A be exercised on a whole batch without the GPU.  The mapping
re-uses System A's own tables and helpers (``LABEL_TO_FIELD``, ``extract_value``, ``DOC_TYPE_TO_PAGE``,
``group_documents``, ``drop_duplicate_copies`` ...), so a label means here exactly what it means to the live
``VisionPipeline``.

What replay can NOT claim, and says so in the result (``extra.replay``):

* a batch item has one reader, no second opinion.  System A would flag every such field ``agreement=False``
  (and V-01 would report E01 for all of them).  ``REPLAY_ASSUME_AGREEMENT=true`` (default) records the single read
  as agreed with ``REPLAY_CONFIDENCE`` so the *rules* can be exercised; ``false`` reproduces System A's strict
  single-reader treatment.  Either way the assumption is written into ``extra.replay`` and ``extractor``.
* a batch item is a whole-row box with its text, there are no column boxes.  Row cells are derived from the
  printed text by a deterministic parser (qty / unit / unit price / amount from the tail of the row).  A row that
  does not parse is **not guessed** - it is skipped and listed in ``extra.replay.skipped_rows``.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

from .batch import BatchDoc

REPLAY_VERSION = "replay/1.0"
NUM = r"\d[\d,]*\.\d{2}"
QTY = r"\d[\d,]*(?:\.\d+)?"
UOM = r"[A-Za-z\u0E01-\u0E4E][A-Za-z0-9\u0E01-\u0E4E./-]{0,11}"
MONEY_GROUP = rf"(?P<money>{NUM}(?:\s+{NUM}){{1,2}})"
ROW_UOM_AFTER_QTY = re.compile(rf"(?P<qty>{QTY})\s+(?P<uom>{UOM})\s+{MONEY_GROUP}\s*$")
ROW_UOM_BEFORE_QTY = re.compile(rf"(?P<uom>{UOM})\s+(?P<qty>\d+(?:\.\d+)?)\s+{MONEY_GROUP}\s*$")
MONEY_OK = re.compile(r"^\d[\d,]*\.\d{2}$")
COMPANY = re.compile(r"(บริษัท|หจก|ห้างหุ้นส่วน|CO\.|LTD|LIMITED|COMPANY|CORP|INC\.?)", re.I)
DATE_ONLY = re.compile(r"^(?:\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2})$")
EMPTY_SIG = ("", "empty", "blank", "none", "unsigned")


def _vp():
    from system_a.perception import vision_pipeline as vp          # imported late: batch/UI code need no engine
    return vp


def _arabic(s: str) -> str:
    from system_a.domain.normalize import thai_to_arabic
    return thai_to_arabic(s)


# ------------------------------------------------------------------------------------------ field values
def candidate(name: str, text) -> tuple:
    """``(value, ok)`` - the printed value of field ``name`` inside ``text``; ``ok`` = it has the shape of one."""
    vp = _vp()
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return None, False
    if name in ("customer_tax_id", "supplier_tax_id"):
        for s in (t, re.sub(r"(?<=\d)[\s\-](?=\d)", "", t)):          # "0-1455-48001-55-7" / "01 45548001557"
            m = vp.TAX_ID_RE.search(_arabic(s))
            if m:
                return s[m.start():m.end()], True
        return t, False
    if name in ("sub_total", "vat", "grand_total"):
        v, _p, _r = vp.extract_value(name, t)
        return v, bool(v and MONEY_OK.match(v.strip()))
    if name == "po_number":
        v, _p, _r = vp.extract_value(name, t)
        return v, bool(v and re.fullmatch(r"\d{6,10}", v.strip()))
    if name == "invoice_date":
        v, _p, _r = vp.extract_value(name, t)
        return v, bool(v and vp.DATE_RE.fullmatch(v.strip()))
    if name == "invoice_num":
        if vp.IDENTIFIER_SHAPE.match(t) and any(c.isdigit() for c in t) and not DATE_ONLY.match(t):
            return t, True
        toks = [x.rstrip("/.-_") for x in vp.TOKEN_RE.findall(t)]
        toks = [x for x in toks if any(c.isdigit() for c in x) and not DATE_ONLY.match(x) and not re.fullmatch(r"\d{13}", x)]
        return (toks[-1], True) if toks else (t, False)
    if name in ("customer_name", "supplier_name"):
        return t, bool(COMPANY.search(t))
    return t, True


def _bbox(it) -> Optional[tuple]:
    b = it.get("bbox_norm")
    return tuple(float(x) for x in b) if b else None


def _union(boxes) -> Optional[tuple]:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return (round(x1, 4), round(y1, 4), round(x2 - x1, 4), round(y2 - y1, 4))


# ------------------------------------------------------------------------------------------ line rows
def parse_row(text: str) -> Optional[dict]:
    """One printed item row -> {description, qty, uom, unit_price, amount}, or None when it is not an item row."""
    t = re.sub(r"\b(THB|BAHT)\b|฿|บาท", " ", str(text or ""), flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    m = ROW_UOM_AFTER_QTY.search(t) or ROW_UOM_BEFORE_QTY.search(t)
    if not m:
        return None
    toks = m.group("money").split()
    try:
        qty = Decimal(m.group("qty").replace(",", ""))
        vals = [Decimal(x.replace(",", "")) for x in toks]
    except InvalidOperation:
        return None
    if len(toks) == 2:
        price, amount = toks
    else:                                           # [weight|price, price|discount, amount] - decide by arithmetic
        a, b, c = vals
        if abs(qty * b - c) <= Decimal("0.01"):
            price = toks[1]
        elif abs(qty * a - c) <= Decimal("0.01"):
            price = toks[0]
        else:
            price = toks[0] if b == 0 else toks[1]
        amount = toks[2]
    return {"description": t[:m.start()].strip() or None, "qty": m.group("qty"), "uom": m.group("uom"),
            "unit_price": price, "amount": amount}


# ------------------------------------------------------------------------------------------ the adapter
def build_replay_extraction(doc: BatchDoc, page_sizes: dict, *, confidence: float = 0.97,
                            assume_agreement: bool = True) -> dict:
    """``BatchDoc`` -> validated ``aiva.extraction/2.0`` dict.  ``page_sizes``: {page: (width_px, height_px)}."""
    vp = _vp()
    from system_a.domain.contracts import (ExtractionResult, PageInfo, RawField, RawLine, Region, SignatureObs)

    by_no = {p.page: p for p in doc.pages}
    page_type, reads, items_by_page = {}, {}, {}
    for p in doc.pages:
        pt = vp.page_type_of(p.doc_type, "SUPPORTING")
        page_type[p.page] = pt
        its = [{"type": i.get("type"), "label": i.get("label"), "text": i.get("text"), "bbox": _bbox(i),
                "bbox_px": i.get("bbox_px"), "confidence": i.get("confidence")} for i in p.kept]
        reads[p.page] = vp.PageRead(page_no=p.page, items=[x for x in its if x["bbox"]], doc_type=p.doc_type,
                                    page_type=pt, error=p.error)
        items_by_page[p.page] = [{**x, "bbox": list(x["bbox"]) if x["bbox"] else None} for x in its]
    invoice_pages = sorted(p for p, t in page_type.items() if t in ("INVOICE", "TAX_INVOICE"))
    fallback_used = False
    if not invoice_pages and page_type:
        invoice_pages, fallback_used = [min(page_type)], True
    documents, inv_doc = vp.group_documents(reads, invoice_pages) if reads else ((), "D1")

    conf0 = float(confidence)
    agree = bool(assume_agreement)

    def conf_of(it) -> float:
        c = float(it.get("confidence") or conf0)
        return c if agree else round(min(c, 0.70), 2)

    # ---- header fields -------------------------------------------------------------------------------
    cands: dict = {}
    for p in sorted(reads):
        for idx, it in enumerate(by_no[p].kept):
            name = vp.LABEL_TO_FIELD.get(str(it.get("label") or "").strip().lower())
            bb = _bbox(it)
            if not name or not bb or not str(it.get("text") or "").strip():
                continue
            val, ok = candidate(name, it.get("text"))
            if val is None:
                continue
            cands.setdefault(name, []).append({"page": p, "idx": idx, "it": it, "bbox": bb, "value": val, "ok": ok})
    fields: dict = {}
    for name, opts in cands.items():
        opts.sort(key=lambda c: (c["page"] not in invoice_pages, not c["ok"], c["page"], c["idx"]))
        best = opts[0]
        if name == "grand_total" and best["ok"]:                      # NET TOTAL beats a 'TOTAL' that is the sub-total
            same = [c for c in opts if c["ok"] and c["page"] == best["page"]]
            best = max(same, key=lambda c: Decimal(c["value"].replace(",", "")))
        if name == "customer_address":                                # an address is often split over several boxes
            same = sorted((c for c in opts if c["page"] == best["page"]), key=lambda c: (c["bbox"][1], c["bbox"][0]))
            raw, box = " ".join(str(c["it"]["text"]).strip() for c in same), _union([c["bbox"] for c in same])
        else:
            raw, box = best["value"], best["bbox"]
        c = conf_of(best["it"])
        fields[name] = RawField(raw=raw, confidence=c, agreement=agree, region=Region(page=best["page"], bbox=box),
                                source="vlm", null_reason=None)
    for req in vp.REQUIRED_FIELD_NAMES:
        fields.setdefault(req, RawField(raw=None, confidence=None, agreement=False, source="vlm",
                                        null_reason="NOT_PRESENT"))
    text_all = " ".join(str(i.get("text") or "") for p in invoice_pages for i in by_no[p].kept)
    if vp._CURRENCY.search(text_all):
        fields["currency"] = RawField(raw="THB", confidence=0.95, agreement=True, source="derived")

    # ---- signatures (same label -> slot mapping and first-wins rule as VisionPipeline._fields) ---------
    signatures: dict = {}
    for p in sorted(reads):
        for it in by_no[p].kept:
            label = str(it.get("label") or "").strip().lower()
            bb = _bbox(it)
            if label in vp.SIGNATURE_LABELS and bb:
                slot = vp.SIGNATURE_LABELS[label]
                if slot not in signatures:
                    txt = str(it.get("text") or "").strip().lower()
                    signatures[slot] = SignatureObs(present=None if txt in EMPTY_SIG else True,
                                                    confidence=float(it.get("confidence") or 0.9), kind=label,
                                                    region=Region(page=p, bbox=bb))

    # ---- lines ---------------------------------------------------------------------------------------
    per_page: dict = {}
    skipped: list = []
    for p in invoice_pages:
        bp = by_no[p]
        rows = []
        for it in sorted((i for i in bp.kept if str(i.get("label") or "").lower().startswith("line_") and _bbox(i)),
                         key=lambda i: (round(_bbox(i)[1], 3), _bbox(i)[0])):
            parsed = parse_row(it.get("text"))
            if not parsed:
                skipped.append({"page": p, "label": it.get("label"), "text": str(it.get("text") or "")[:120],
                                "reason": "not an item row (no qty / unit / price / amount at the end)"})
                continue
            bb, c = _bbox(it), conf_of(it)
            cells = {}
            for col, raw in parsed.items():
                if raw is None:
                    continue
                cells[col] = RawField(raw=str(raw), confidence=c, agreement=agree, region=Region(page=p, bbox=bb),
                                      source="derived")
            rows.append((cells, Region(page=p, bbox=bb)))
        per_page[p] = rows
    kept_rows, copy_notes = vp.drop_duplicate_copies(per_page, {p: page_type[p] for p in per_page},
                                                     {p: vp.page_identity(reads[p]) for p in per_page})
    lines = tuple(RawLine(line_no=n, region=region, cells=cells) for n, (cells, region) in enumerate(kept_rows, start=1))

    # ---- pages / extra -------------------------------------------------------------------------------
    infos = []
    for p in doc.pages:
        w_px, h_px = page_sizes.get(p.page) or (1240, 1754)
        infos.append(PageInfo(page_no=p.page, width_pt=round(w_px * 72 / 150, 2), height_pt=round(h_px * 72 / 150, 2),
                              render_dpi=150, page_type=page_type[p.page]))
    sha = "sha256:" + hashlib.sha256(json.dumps([[i for i in pg.kept] for pg in doc.pages], sort_keys=True,
                                                ensure_ascii=False, default=str).encode()).hexdigest()
    extra = {
        "items_by_page": {str(p): v for p, v in items_by_page.items()},
        "dropped_items": [{"type": i.get("type"), "label": i.get("label"), "text": i.get("text"),
                           "bbox_2d": None, "drop_reason": i.get("drop_reason"), "page": p.page}
                          for p in doc.pages for i in p.dropped],
        "doc_type_by_page": {str(p.page): p.doc_type for p in doc.pages},
        "coord_mode_by_page": {str(p.page): p.coord for p in doc.pages},
        "seconds_by_page": {str(p.page): p.seconds for p in doc.pages},
        "page_errors": {str(p.page): p.error for p in doc.pages if p.error},
        "invoice_pages": invoice_pages, "pages_total": doc.pages_total or len(doc.pages),
        "replay": {"version": REPLAY_VERSION, "assume_agreement": agree, "confidence_when_missing": conf0,
                   "invoice_page_fallback": fallback_used, "skipped_rows": skipped, "copy_pages_dropped": copy_notes,
                   "note": "single OCR read per field; row cells derived from printed text (no column boxes)"},
    }
    ext = ExtractionResult(
        package_id=f"BATCH-{doc.id}", dms_doc_id=str(doc.id), file_sha256=sha, pages=tuple(infos), documents=documents,
        invoice_document_id=inv_doc, pages_complete=not any(p.error for p in doc.pages), fields=fields, lines=lines,
        signatures=signatures, extra=extra,
        extractor={"ocr": "batch-report", "pipeline": REPLAY_VERSION,
                   "agreement": "assumed (single read)" if agree else "strict (single read = not agreed)"})
    return ext.model_dump(mode="json")
