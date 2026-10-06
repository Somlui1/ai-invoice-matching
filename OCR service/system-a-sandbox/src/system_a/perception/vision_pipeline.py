"""Real perception: DMS PDF -> ``ExtractionResult`` with bboxes at every level (Qwen VLM + PDF text layer).

Passes, per document
  1. **ingest**      sha256, page geometry (DPI, ``/Rotate``), render, PDF text-layer words — no LLM.
  2. **page items**  one VLM call per page -> ``doc_type`` + every readable region with ``bbox_2d``.
  3. **classify**    page-type votes: the page-items answer is vote 1, a dedicated classify call is vote 2,
                     a third vote runs only when the first two disagree (early stop keeps 99 docs runnable).
  4. **table rows**  one call per invoice page -> item rows with one box per cell.
  5. **crop re-read** a zoomed crop per critical field -> a third, independent read.

Consensus rule (Standard OQ-09, "ห้ามเดา"): a value counts as *agreed* only when two independent readers
(VLM page read / PDF text layer / zoomed crop read) produce the same string.  A single unverified read is
kept but flagged ``agreement=False`` with a reduced confidence, which the domain layer turns into a review.
Nothing is discarded silently: every region the model returned but that failed a sanity check is kept in
``extra["dropped_items"]`` together with its reason, and every failed call is kept in ``calls``.
"""
from __future__ import annotations

import base64
import difflib
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field as dc_field
from statistics import mean
from typing import Optional

from ..domain.contracts import (DocumentInfo, ExtractionResult, RawField, RawLine, Region,
                                RegionNode, SignatureObs, Word)
from ..domain.normalize import thai_to_arabic
from ..domain.standard import load_prompt, load_standard
from .coords import (bbox_problems, choose_coord_mode, coord_overflow, filter_items, union_box, words_in_box,
                     xywh_to_pt, xyxy_to_xywh)
from .pdf_ingest import crop_png, ingest_pdf, page_text_and_words
from .text_layer import layer_unreliable

PROMPTS = ("vision_page_items", "vision_page_classify", "vision_table_rows", "vision_crop_reread")


def _code_fingerprint() -> str:
    """Hash of the perception code that produces an extraction.

    A cached result is only valid for the code that made it, so the batch cache is keyed on this as well as
    on the file hash, model and prompt versions — changing the algorithm invalidates the cache by itself.
    """
    import hashlib
    import inspect

    from . import coords, pdf_ingest
    h = hashlib.sha256()
    for mod in (pdf_ingest, coords, sys.modules[__name__]):
        try:
            with open(inspect.getsourcefile(mod), "rb") as fh:
                h.update(fh.read())
        except OSError:                              # pragma: no cover - frozen build has no source
            h.update(mod.__name__.encode())
    return h.hexdigest()[:12]


CODE_VERSION = _code_fingerprint()

#: prompt label -> System A field name (aliases cover spellings the model still produces)
LABEL_TO_FIELD = {
    "doc_no": "invoice_num", "invoice_no": "invoice_num", "invoice_number": "invoice_num",
    "doc_date": "invoice_date", "invoice_date": "invoice_date",
    "po_number": "po_number", "po_no": "po_number", "po": "po_number",
    "supplier_name": "supplier_name", "vendor_name": "supplier_name",
    "supplier_address": "supplier_address", "vendor_address": "supplier_address",
    "supplier_tax_id": "supplier_tax_id", "tax_id": "supplier_tax_id", "tax_id_no": "supplier_tax_id",
    "customer_name": "customer_name", "buyer_name": "customer_name",
    "customer_address": "customer_address", "buyer_address": "customer_address",
    "customer_tax_id": "customer_tax_id", "buyer_tax_id": "customer_tax_id",
    "sub_total": "sub_total", "subtotal": "sub_total", "total_excl_vat": "sub_total",
    "vat": "vat", "vat_amount": "vat", "tax_amount": "vat",
    "grand_total": "grand_total", "total_amount": "grand_total", "total": "grand_total",
}
#: Fields a crop re-read is worth paying for: the eight V-01 requires, plus the two identifiers the rules
#: and the report lean on.  A crop is an independent reader, so it is only asked when the page read and the
#: PDF text layer do not already agree.
CRITICAL_FIELDS = ("invoice_num", "po_number", "customer_name", "customer_address", "customer_tax_id",
                   "sub_total", "vat", "grand_total", "supplier_tax_id", "invoice_date", "supplier_name")

#: the printed shape each field must have.  A reader whose value does not have it does not vote (DMS-25: a crop of
#: the wrong box read the postal code "13160" as the customer Tax ID and out-voted the correct VLM value).
_SHAPES = {"customer_tax_id": re.compile(r"^\d{13}$"), "supplier_tax_id": re.compile(r"^\d{13}$"),
           "po_number": re.compile(r"^\d{8,10}$"),
           "sub_total": re.compile(r"^\d[\d,]*\.\d{2}$"), "vat": re.compile(r"^\d[\d,]*\.\d{2}$"),
           "grand_total": re.compile(r"^\d[\d,]*\.\d{2}$")}
PO_IN_TEXT = re.compile(r"(?<![\dA-Za-z])(\d{8})(?:-(\d{1,4}))?(?![\d])")


def shape_ok(name: str, value) -> bool:
    """True when ``value`` has the printed shape of field ``name`` (fields without a shape rule always pass)."""
    pat = _SHAPES.get(name)
    if pat is None or value is None:
        return value is not None
    v = thai_to_arabic(str(value)).strip()
    if name.endswith("tax_id"):
        v = re.sub(r"[\s\-]", "", v)
    if name == "po_number":
        v = re.sub(r"\D", "", v.split("-")[0])
    return bool(pat.match(v))
CELL_LABELS = {"description": "description", "desc": "description", "item": "description",
               "item_desc": "description", "qty": "qty", "quantity": "qty", "uom": "uom", "unit": "uom",
               "unit_price": "unit_price", "price": "unit_price", "rate": "unit_price",
               "amount": "amount", "total_amount": "amount"}
DOC_TYPE_TO_PAGE = {
    "tax_invoice": "TAX_INVOICE", "tax_invoice_receipt": "TAX_INVOICE", "invoice": "INVOICE",
    "purchase_order": "PO", "po": "PO", "osp": "OSP", "delivery_note": "DELIVERY_NOTE",
    "goods_receipt": "DELIVERY_NOTE", "receipt": "SUPPORTING", "billing_note": "SUPPORTING",
    "credit_note": "SUPPORTING", "debit_note": "SUPPORTING", "quotation": "SUPPORTING",
    "payment_voucher": "SUPPORTING", "withholding_tax_cert": "SUPPORTING", "other": "SUPPORTING",
    "unknown": "UNKNOWN",
}
PAGE_TYPES = set(DOC_TYPE_TO_PAGE.values()) - {"UNKNOWN"} | {"UNKNOWN"}
SIGNATURE_LABELS = {"receiver_signature": "receiver", "deliverer_signature": "deliverer",
                    "authorized_signature": "receiver", "approver_signature": "receiver"}
REQUIRED_FIELD_NAMES = ("invoice_num", "po_number", "customer_name", "customer_address", "customer_tax_id",
                        "sub_total", "vat", "grand_total", "supplier_name", "supplier_tax_id", "invoice_date")
_CURRENCY = re.compile(r"(THB|฿|บาท|BAHT)", re.I)


#: Thai combining marks (sara, tone marks, thanthakhat).  The DMS text layer is OCRmyPDF/Tesseract output
#: produced without Thai language data, which drops or reorders them, so they are folded away **for
#: comparison only** — the stored ``raw_value`` always keeps exactly what the reader saw.
THAI_MARKS = re.compile(r"[\u0E31\u0E33\u0E34-\u0E3A\u0E47-\u0E4E]")


def _cmp(s) -> str:
    t = THAI_MARKS.sub("", unicodedata.normalize("NFKC", str(s or "")))
    return re.sub(r"\s+", "", thai_to_arabic(t)).casefold()


_NUM = re.compile(r"^\d{1,3}(?:[.,]\d{3})+[.,]\d{1,2}$|^\d{1,3}(?:[.,]\d{3})+$|^\d+[.,]\d{1,2}$|^\d+$")


def _num(s):
    """Canonical value of a printed number, so ``1,234.00`` / ``1.234,00`` / ``1234.00`` are one value.

    Only separators that fit a real thousands/decimal pattern are folded: ``12.34`` never equals
    ``1234``, and an integer never equals its 2-decimal form (that difference is real evidence).
    """
    t = _cmp(s)
    if not _NUM.match(t):
        return None
    parts = re.split(r"[.,]", t)
    if len(parts) == 1:
        return parts[0]
    if len(parts) > 2 or len(parts[-1]) != 3:
        return "".join(parts[:-1]) + "." + parts[-1]
    return "".join(parts)


def _key(s) -> str:
    return _num(s) or _cmp(s)


#: The VLM reads a printed *block* ("รวมมูลค่าสินค้า / SUB TOTAL 25,432.00"), the PDF text layer reads the
#: same block with different label noise, and a zoomed crop reads only the value.  The value is pulled out
#: with one deterministic pattern per field family, so three readers that all saw ``25,432.00`` are
#: recognised as agreeing - and so the numeric normaliser is never handed a label as if it were a number.
MONEY_RE = re.compile(r"\d[\d.,]*\d|\d")
TAX_ID_RE = re.compile(r"(?<!\d)\d{13}(?!\d)")
PO_RE = re.compile(r"(?<!\d)\d{6,10}(?!\d)")
DATE_RE = re.compile(r"(?<!\d)(?:\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-](?:\d{4}|\d{2}))(?!\d)")
VALUE_PATTERNS = {"sub_total": MONEY_RE, "vat": MONEY_RE, "grand_total": MONEY_RE, "discount": MONEY_RE,
                  "wht": MONEY_RE, "total_qty": MONEY_RE, "customer_tax_id": TAX_ID_RE,
                  "supplier_tax_id": TAX_ID_RE, "po_number": PO_RE, "invoice_date": DATE_RE,
                  "doc_date": DATE_RE, "due_date": DATE_RE}
_TAKE_FIRST = {"customer_tax_id", "supplier_tax_id", "invoice_date", "doc_date", "due_date"}

#: Fields whose value has to leave the document as one machine-readable token (``invoice_num`` is bound into
#: the EBS receipt lookup).  ``IDENTIFIER_SHAPE`` is the shape such a value has once the label is off - the
#: same shape ``adapters/oracle/sql_guard.py`` will accept - and it is how the pipeline notices that a region
#: is still holding "เลขที่ NUMBER 26/2691" rather than the number "26/2691".
VALUE_TOKEN_FIELDS = {"invoice_num"}
IDENTIFIER_SHAPE = re.compile(r"^[A-Za-z0-9/\-_.]{1,40}$")

#: free-text fields, judged by measured similarity rather than by character equality
FREE_TEXT_FIELDS = {"supplier_name", "supplier_address", "customer_name", "customer_address",
                  "description"}
TEXT_AGREEMENT_SIMILARITY = 0.85
TEXT_AGREEMENT_CONFIDENCE = 0.85


def extract_value(name: str, text, crop_text=None) -> tuple:
    """``(value, printed_text, rule)`` - the printed value of a field, without the words around it.

    ``value`` is a substring of that reader's own text (never a rewrite), ``printed_text`` keeps the whole
    region so the evidence still shows the label that was read, and ``rule`` names how the value was found.
    """
    printed = None if text is None else str(text).strip()
    if not printed:
        return None, None, "empty"
    pattern = VALUE_PATTERNS.get(name)
    if pattern:
        arabic = thai_to_arabic(printed)                    # same length, so spans map back 1:1
        spans = [m.span() for m in pattern.finditer(arabic)]
        if spans:
            a, b = spans[0] if name in _TAKE_FIRST else spans[-1]
            return printed[a:b], printed, "pattern:" + pattern.pattern
    if crop_text:
        crop = str(crop_text).strip()
        if crop and _cmp(crop) and _cmp(crop) in _cmp(printed):
            return crop, printed, "crop_value_inside_region"
    return printed, printed, "whole_region"



def shaped_value(name: str, text):
    """The last occurrence in ``text`` of a value with ``name``'s printed shape (``"ร ว ม 49,215.00 ‘4"`` -> 49,215.00)."""
    pattern = VALUE_PATTERNS.get(name)
    if not pattern or not text:
        return None
    arabic = thai_to_arabic(str(text))
    hits = [str(text)[a:b] for a, b in (m.span() for m in pattern.finditer(arabic))]
    good = [h for h in hits if shape_ok(name, h)]
    if not good:
        return None
    return good[0] if name in _TAKE_FIRST else good[-1]


NAME_START = re.compile(r"(บริษัท|ห้างหุ้นส่วน|หจก\.?|[A-Z][A-Za-z&.,'\- ]{2,}(?:CO\.|COMPANY|LTD|LIMITED|CORP))", re.I)
NAME_FIELDS = {"customer_name", "supplier_name"}


def strip_label(name: str, text):
    """``ชื่อผู้ซื้อ SOLD TO บริษัท ... จำกัด`` -> ``บริษัท ... จำกัด`` (labels printed in front of a company name)."""
    if name not in NAME_FIELDS or not text:
        return text
    t = str(text)
    i = t.find("บริษัท")
    if i < 0:
        i = t.find("ห้างหุ้นส่วน")
    if i <= 0 or re.search(r"\b(CO\.|COMPANY|LTD|LIMITED|CORP|INC)\b", t[:i], re.I):
        return t                          # nothing in front, or an English company name (bilingual, not a label)
    return t[i:].strip()


def same_text(a, b) -> bool:
    """Two readers agree when the strings match after whitespace/case/Thai-digit/Thai-mark folding, or when
    both are the same printed number written with different separators (``1,234.00`` == ``1234.00``)."""
    if a is None or b is None or not str(a).strip() or not str(b).strip():
        return False
    x, y = _cmp(a), _cmp(b)
    if x == y:
        return True
    na, nb = _num(a), _num(b)
    return na is not None and na == nb


def prompt_identity(name: str, text: str) -> str:
    m = re.search(r"prompt_id:\s*([a-z0-9_-]+)\s+version:\s*([0-9.]+)", text[:200])
    return f"{m.group(1)}@{m.group(2)}" if m else f"{name}@unversioned"


def page_type_of(value, fallback: str = "UNKNOWN") -> str:
    key = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    mapped = DOC_TYPE_TO_PAGE.get(key)
    if mapped:
        return mapped
    upper = key.upper()
    return upper if upper in PAGE_TYPES else fallback


@dataclass
class PageRead:
    page_no: int
    items: list = dc_field(default_factory=list)
    dropped: list = dc_field(default_factory=list)
    doc_type: str = "unknown"
    page_type: str = "UNKNOWN"
    type_confidence: Optional[float] = None
    votes: list = dc_field(default_factory=list)
    is_copy: Optional[bool] = None
    coord_mode: str = "auto"
    coord_overflow: Optional[dict] = None
    ocr_quality: Optional[float] = None
    error: Optional[str] = None


@dataclass
class _Ctx:
    pdf: bytes
    infos: dict
    pngs: dict
    layers: dict


class VisionPipeline:
    """Qwen page-items + PDF text layer perception (the production path for real DMS documents)."""

    def __init__(self, client, model: str, *, dpi: int = 150, crop_dpi: int = 300, coord: str = "auto",
                 max_pages: int = 12, max_tokens: int = 8000, table_pages: int = 8, critical_crops: int = 16,
                 do_table: bool = True, do_crops: bool = True, do_classify: bool = True,
                 json_mode: bool = False, max_words: int = 2500, crop_pad_pt: float = 8.0,
                 message_layout: str = "v3", cell_box: str = "row"):
        self.client, self.model = client, model
        self.dpi, self.crop_dpi, self.coord, self.max_pages = dpi, crop_dpi, coord, max_pages
        self.max_tokens, self.table_pages, self.critical_crops = max_tokens, table_pages, critical_crops
        self.do_table, self.do_crops, self.do_classify = do_table, do_crops, do_classify
        self.json_mode, self.max_words = json_mode, max_words
        self.message_layout, self.cell_box = message_layout, cell_box
        self.crop_dpi = float(crop_dpi)
        self.crop_pad_pt = float(crop_pad_pt)
        self.prompts = {name: load_prompt(name) for name in PROMPTS}
        self.prompt_version = "+".join(prompt_identity(n, self.prompts[n]) for n in PROMPTS)
        self.code_version = CODE_VERSION
        self.calls: list[dict] = []
        self.stats: dict = {}
        try:                                   # the units the Standard knows (a unit outside it stays unverified)
            self.uom_vocab = {str(m).upper().rstrip(".") for ms in load_standard().uom_groups.values() for m in ms}
        except Exception:
            self.uom_vocab = set()

    # ------------------------------------------------------------------ one VLM call
    def _ask(self, kind: str, prompt_name: str, png: bytes, instruction: str, page_no) -> dict:
        b64 = base64.b64encode(png).decode()
        entry = {"kind": kind, "page": page_no, "model": self.model}
        t0 = time.time()
        try:
            out = self.client.chat_json(self.model, self.prompts[prompt_name], instruction, layout=self.message_layout,
                                        images=[f"data:image/png;base64,{b64}"], temperature=0,
                                        max_tokens=self.max_tokens, json_mode=self.json_mode)
        except Exception as e:  # recorded per call; the caller decides what a failure means for the document
            self.calls.append({**entry, "ok": False, "ms": round((time.time() - t0) * 1000),
                               "error": f"{type(e).__name__}: {str(e)[:200]}"})
            raise
        self.calls.append({**entry, "ok": True, "ms": round((time.time() - t0) * 1000),
                           "usage": dict(getattr(self.client, "last_usage", {}) or {})})
        return out if isinstance(out, dict) else {}

    # ------------------------------------------------------------------ document pipeline
    def extract(self, pdf: bytes, *, package_id: str, dms_doc_id: str) -> ExtractionResult:
        call_start = len(self.calls)
        sha, rendered = ingest_pdf(pdf, dpi=self.dpi)
        layers = {row["page"]: row for row in page_text_and_words(pdf)}
        used = rendered[:self.max_pages]
        truncated = len(rendered) > self.max_pages
        ctx = _Ctx(pdf=pdf, infos={r.info.page_no: r.info for r in rendered},
                   pngs={r.info.page_no: r.png for r in rendered}, layers=layers)
        reads: dict[int, PageRead] = {}
        for rp in used:
            read = self._read_page(rp, ctx)
            reads[rp.info.page_no] = read

        invoice_pages = sorted(p for p, r in reads.items() if r.page_type in ("INVOICE", "TAX_INVOICE"))
        if not invoice_pages and reads:
            invoice_pages = [min(reads)]        # nothing classified as an invoice: page 1 carries the document
        documents, inv_doc_id = group_documents(reads, invoice_pages)
        words, words_skipped = self._words(ctx, invoice_pages)
        fields, signatures, regions, crop_log = self._fields(ctx, reads, invoice_pages)
        lines, table_regions, row_errors, lines_source, table_notes = self._lines(ctx, reads, invoice_pages)
        regions = regions + table_regions + self._section_regions(reads)
        currency = self._currency(ctx, invoice_pages)
        if currency is not None:
            fields["currency"] = currency

        corroborations = corroborate(fields, lines, self.uom_vocab)
        pages_out = tuple(r.info.model_copy(update={"page_type": reads[r.info.page_no].page_type,
                                                    "type_confidence": reads[r.info.page_no].type_confidence,
                                                    "ocr_quality": reads[r.info.page_no].ocr_quality})
                          if r.info.page_no in reads else r.info for r in used)
        ext = ExtractionResult(
            package_id=package_id, dms_doc_id=dms_doc_id, file_sha256=sha,
            pages=pages_out, documents=documents, invoice_document_id=inv_doc_id,
            pages_complete=not truncated and not any(r.error for r in reads.values()),
            fields=fields, lines=lines, signatures=signatures, words=words, regions=tuple(regions),
            extra={
                "ocr_text_by_page": {str(p): (layers.get(p, {}).get("text") or "")[:20000] for p in reads},
                "text_layer_chars_by_page": {str(p): layers.get(p, {}).get("text_layer_chars", 0) for p in reads},
                "doc_type_by_page": {str(p): reads[p].doc_type for p in reads},
                "page_type_votes": {str(p): reads[p].votes for p in reads},
                "is_copy_by_page": {str(p): reads[p].is_copy for p in reads},
                "coord_mode_by_page": {str(p): reads[p].coord_mode for p in reads},
                "coord_overflow": {str(p): reads[p].coord_overflow for p in reads if reads[p].coord_overflow},
                "ocr_quality_by_page": {str(p): reads[p].ocr_quality for p in reads},
                "items_by_page": {str(p): [{k: it.get(k) for k in ("type", "label", "text", "bbox", "confidence",
                                                                   "bbox_vlm", "bbox_method")}
                                           for it in reads[p].items] for p in reads},
                "dropped_items": [{k: it.get(k) for k in ("type", "label", "text", "bbox_2d", "drop_reason")}
                                  | {"page": p} for p in reads for it in reads[p].dropped],
                "page_errors": {str(p): reads[p].error for p in reads if reads[p].error},
                "row_errors": row_errors, "lines_source": lines_source, "crop_reads": crop_log,
                "table_notes": table_notes,
                "corroborations": corroborations,
                "calls": self.calls[call_start:],
                "words_capped_at": self.max_words, "words_skipped": words_skipped,
                "truncated_pages": truncated, "render_dpi": self.dpi, "crop_dpi": self.crop_dpi,
                "invoice_pages": invoice_pages, "pages_total": len(rendered),
            },
            extractor={"vlm": self.model, "prompts": self.prompt_version, "ocr": "pdf-text-layer(pymupdf)",
                       "pipeline": f"vision-pipeline/{CODE_VERSION}"})
        problems = bbox_problems(element_boxes(ext))
        if problems:
            ext.extra["bbox_problems"] = problems
        self.stats = {"calls": len(self.calls), "ok": sum(1 for c in self.calls if c["ok"]),
                      "failed": sum(1 for c in self.calls if not c["ok"]),
                      "ms": round(sum(int(c.get("ms") or 0) for c in self.calls)),
                      "pages": len(reads), "items": sum(len(r.items) for r in reads.values()),
                      "dropped_items": sum(len(r.dropped) for r in reads.values()),
                      "fields": len(fields), "lines": len(lines), "words": len(words),
                      "by_kind": dict(Counter(c["kind"] for c in self.calls))}
        return ext

    def _read_page(self, rp, ctx: _Ctx) -> PageRead:
        info = rp.info
        img_w = max(1, round(info.width_pt * self.dpi / 72))
        img_h = max(1, round(info.height_pt * self.dpi / 72))
        read = PageRead(page_no=info.page_no)
        try:
            raw = self._ask("page_items", "vision_page_items", rp.png,
                            "Read this single page and return the JSON described above.", info.page_no)
        except Exception as e:
            read.error = f"page_items: {e}"
            return read
        if getattr(self.client, "last_salvaged", False):
            # The answer arrived as truncated JSON and only its complete members were kept.  The items we
            # did get are used, but the page must not count as fully read: a silently missing row could
            # otherwise hide an under-declared invoice line.
            read.error = "page_items: truncated JSON answer, only complete members kept"
        read.doc_type = (str(raw.get("doc_type") or "unknown").strip().lower() or "unknown")
        read.items, read.dropped, read.coord_mode = filter_items(
            raw.get("items") or [], img_w, img_h, self.coord, ctx.layers.get(info.page_no, {}).get("words", []))
        read.coord_overflow = coord_overflow(raw.get("items") or [], img_w, img_h, read.coord_mode)
        # boxes are Qwen's own (as in bbox_testv3).  The PDF text layer is NOT used to move them: it is the
        # OCRmyPDF/Tesseract layer of the archive, positioned per line, and moving boxes onto it measured worse.
        read.votes = [page_type_of(read.doc_type, "SUPPORTING")]
        read.ocr_quality = page_quality(read.items, ctx.layers.get(info.page_no, {}).get("words", []))
        if self.do_classify:
            self._classify(read, rp.png)
        return read

    # ------------------------------------------------------------------ classification votes
    def _classify(self, read: PageRead, png: bytes) -> None:
        for attempt, instruction in ((1, "Classify this page."),
                                     (2, "Classify this page again, from scratch.")):
            try:
                out = self._ask("classify", "vision_page_classify", png, instruction, read.page_no)
            except Exception as e:
                read.error = ((read.error or "") + f" | classify{attempt}: {e}").strip(" |")
                break
            read.votes.append(page_type_of(out.get("page_type")))
            if isinstance(out.get("is_copy"), bool):
                read.is_copy = out["is_copy"]
            if read.votes[0] == read.votes[-1]:
                break                                   # two independent readers agree -> stop
        tally = Counter(read.votes)
        read.page_type, votes_for = tally.most_common(1)[0] if tally else ("UNKNOWN", 0)
        read.type_confidence = round(votes_for / max(1, len(read.votes)), 2)

    # ------------------------------------------------------------------ words / fields / lines
    def _words(self, ctx: _Ctx, invoice_pages: list) -> tuple[tuple[Word, ...], int]:
        """Word boxes come from the PDF text layer (exact, no model).  Capped per document so the result
        JSON and the HTML report stay deliverable; the number skipped is reported, never hidden."""
        out, skipped = [], 0
        for p in sorted(ctx.layers):
            for w in ctx.layers[p]["words"]:
                if len(out) >= self.max_words and (p not in invoice_pages or len(out) >= self.max_words * 2):
                    skipped += 1
                    continue
                out.append(Word(word_id=w["word_id"], page=p, text=w["text"], bbox=w["bbox"], confidence=1.0))
        return tuple(out), skipped

    def _fields(self, ctx: _Ctx, reads: dict, invoice_pages: list):
        fields: dict[str, RawField] = {}
        signatures: dict[str, SignatureObs] = {}
        regions: list[RegionNode] = []
        crop_log: list[dict] = []
        crops_used = 0
        first_invoice = invoice_pages[0] if invoice_pages else None
        candidates: dict[str, list] = defaultdict(list)
        for p in sorted(reads):
            for it in reads[p].items:
                name = LABEL_TO_FIELD.get(str(it.get("label") or "").strip().lower())
                if name:
                    candidates[name].append((p, it))

        for name, options in candidates.items():
            page, it = pick_candidate(name, options, first_invoice)
            page_words = ctx.layers.get(page, {}).get("words", [])
            inside = words_in_box(page_words, it["bbox"])
            layer_text = " ".join(w["text"] for w in inside) or None
            # A layer without Thai language data shreds Thai into glyphs: it cannot vote on such a region.
            # Counting it as a reader turned every Thai name into CONFLICT/LOW_CONFIDENCE (DMS-15/19/23/25).
            # Fields with a printed-value pattern (money, Tax ID, PO, date) keep the layer's vote when the layer holds a
            # value of that shape among the Thai noise ("ร ว ม 49,215.00" still reads 49,215.00).
            layer_shaped = shaped_value(name, layer_text) is not None
            layer_abstained = layer_unreliable(layer_text) and not layer_shaped
            layer_vote = None if layer_abstained else layer_text
            vlm_value_0, _p0, vlm_rule_0 = extract_value(name, it.get("text"))
            needs_another_reader = layer_vote is None or not same_text(it.get("text"), layer_vote) or (
                name in VALUE_TOKEN_FIELDS and vlm_rule_0 == "whole_region"
                and not IDENTIFIER_SHAPE.match(str(it.get("text") or "")))
            want_crop = (self.do_crops and name in CRITICAL_FIELDS and crops_used < self.critical_crops
                         and needs_another_reader)
            crop_text = self._crop_read(ctx, name, page, it["bbox"]) if want_crop else None
            if want_crop:
                crops_used += 1
            vlm_value, _vlm_printed, vlm_rule = extract_value(name, it.get("text"), crop_text)
            vlm_value = shaped_value(name, it.get("text")) or strip_label(name, vlm_value)
            layer_value = (shaped_value(name, layer_vote) or extract_value(name, layer_vote, crop_text)[0]) \
                if layer_vote else None
            crop_value, _crop_printed, _crop_rule = extract_value(name, crop_text)
            crop_value = shaped_value(name, crop_text) or strip_label(name, crop_value)
            votes = {"vlm": vlm_value or strip_label(name, it.get("text")), "text_layer": layer_value or layer_vote,
                     "crop": crop_value or crop_text}
            # a reading without the field's printed shape is not a vote (when at least one reading has it)
            shaped = {k: v for k, v in votes.items() if v and shape_ok(name, v)}
            rejected = sorted(k for k, v in votes.items() if v and k not in shaped) if shaped else []
            if shaped:
                votes = {k: (v if k in shaped else None) for k, v in votes.items()}
            raw, conf, agree, source, null_reason = consensus(votes["vlm"], votes["text_layer"], votes["crop"],
                                                              float(it.get("confidence") or 0),
                                                              fuzzy=name in FREE_TEXT_FIELDS)
            readers = [v for v in (vlm_value, layer_value, crop_value) if v]
            similarity = round(closest_pair(readers)[0], 3) if len(readers) >= 2 else None
            fields[name] = RawField(raw=raw, confidence=conf, agreement=agree,
                                    region=Region(page=page, bbox=it["bbox"]),
                                    word_ids=tuple(w["word_id"] for w in inside)[:40],
                                    source=source, null_reason=null_reason)
            crop_log.append({"field": name, "page": page, "vlm": it.get("text"), "text_layer": layer_text,
                             "text_layer_abstained": layer_abstained, "votes_rejected_by_shape": rejected,
                             "crop": crop_text, "value": raw, "value_rule": vlm_rule,
                             "readers_similarity": similarity, "bbox_method": it.get("bbox_method"),
                             "bbox_vlm": it.get("bbox_vlm"),
                             "judged": "similarity" if name in FREE_TEXT_FIELDS else "exact",
                             "agreed": agree, "confidence": conf, "source": source})

        po_from_lines(fields, reads, invoice_pages, crop_log, ctx.layers)
        reconcile_grand_total(fields, candidates, crop_log)

        for p in sorted(reads):
            for it in reads[p].items:
                label = str(it.get("label") or "").strip().lower()
                if label in SIGNATURE_LABELS:
                    slot = SIGNATURE_LABELS[label]
                    if slot in signatures:
                        continue
                    text = str(it.get("text") or "").strip().lower()
                    signatures[slot] = SignatureObs(
                        present=None if text in ("", "empty", "blank", "none") else True,
                        confidence=float(it.get("confidence") or 0.5), kind=label,
                        region=Region(page=p, bbox=it["bbox"]))
        for req in REQUIRED_FIELD_NAMES:
            fields.setdefault(req, RawField(raw=None, confidence=None, agreement=False, source="vlm",
                                            null_reason="NOT_PRESENT"))
        return fields, signatures, regions, crop_log

    def _crop_read(self, ctx: _Ctx, name: str, page: int, bbox) -> Optional[str]:
        info = ctx.infos[page]
        png = crop_png(ctx.pdf, page, xywh_to_pt(bbox, info.width_pt, info.height_pt), dpi=self.crop_dpi,
                       pad_pt=self.crop_pad_pt)
        if not png:
            return None
        try:
            out = self._ask("crop_reread", "vision_crop_reread", png,
                            f"Read the {name.replace('_', ' ')} printed in this crop.", page)
        except Exception:
            return None
        raw = out.get("raw")
        return None if raw is None or str(raw).strip() == "" else str(raw).strip()

    def _lines(self, ctx: _Ctx, reads: dict, invoice_pages: list):
        lines: list[RawLine] = []
        regions: list[RegionNode] = []
        errors: list[dict] = []
        notes: list[dict] = []
        source = {"table_rows": 0, "line_items": 0}
        per_page: dict[int, list] = {}
        for order, page in enumerate(sorted(invoice_pages)):
            read = reads.get(page)
            if read is None:
                continue
            info = ctx.infos[page]
            img_w = max(1, round(info.width_pt * self.dpi / 72))
            img_h = max(1, round(info.height_pt * self.dpi / 72))
            page_words = ctx.layers.get(page, {}).get("words", [])
            rows = None
            if self.do_table and order < self.table_pages:
                try:
                    raw = self._ask("table_rows", "vision_table_rows", ctx.pngs[page],
                                    "Digitise the item table of this page.", page)
                    parsed = parse_table_rows(raw, img_w, img_h, page, words=page_words)
                    rows, rows_notes = parsed["rows"], parsed.get("notes") or []
                    if raw.get("table_bbox"):
                        regions.append(RegionNode(region_id=f"T{page}-001", page=page, kind="table",
                                                  label="item_table", bbox=parsed["table_bbox"],
                                                  confidence=0.9))
                    for i, col in enumerate(parsed["columns"], start=1):
                        regions.append(RegionNode(region_id=f"T{page}-C{i:02d}", page=page, kind="section",
                                                  label=f"column:{col['label']}", bbox=col["bbox"]))
                    notes.extend(rows_notes)
                    source["table_rows"] += len(rows)
                except Exception as e:
                    errors.append({"page": page, "stage": "table_rows",
                                   "error": f"{type(e).__name__}: {str(e)[:180]}"})
                    rows = None
            if rows is None:
                rows = rows_from_line_items(read)
                source["line_items"] += len(rows)
            page_rows: list = []
            for row in rows:
                cells = {}
                if self.cell_box == "row":
                    # bbox_testv3 highlights FULL ROWS from the page read.  Cell boxes of the second (table) call
                    # measured off-target more often (22 % vs 14 %), so a cell is shown on the page-read row that
                    # holds it; the table call still supplies the cell TEXT.
                    rb = row_box_from_page(read, row.get("bbox"))
                    if rb is not None:
                        row["bbox"] = rb
                        for cell in row["cells"].values():
                            if cell.get("bbox") or cell.get("text"):
                                cell["bbox"] = rb
                for col, cell in row["cells"].items():
                    if col not in CELL_LABELS:
                        continue
                    name = CELL_LABELS[col]
                    inside = words_in_box(page_words, cell["bbox"]) if cell.get("bbox") else []
                    layer_text = " ".join(w["text"] for w in inside) or None
                    agree = same_text(cell.get("text"), layer_text) or same_text(
                        re.sub(r"[^0-9A-Za-z.,]", "", str(cell.get("text") or "")),
                        re.sub(r"[^0-9A-Za-z.,]", "", str(layer_text or "")))
                    conf = 0.96 if agree else round(min(float(cell.get("confidence") or 0.6), 0.7), 2)
                    cells[name] = RawField(raw=cell.get("text"), confidence=conf, agreement=agree,
                                           region=Region(page=page, bbox=cell["bbox"]) if cell.get("bbox") else None,
                                           word_ids=tuple(w["word_id"] for w in inside)[:20],
                                           source="consensus" if agree else "vlm",
                                           null_reason=None if cell.get("text") else "NOT_PRESENT")
                page_rows.append((cells, Region(page=page, bbox=row["bbox"]) if row.get("bbox") else None))
            per_page[page] = page_rows
        kept, copy_notes = drop_duplicate_copies(
            per_page,
            {p: (reads[p].page_type if p in reads else "UNKNOWN") for p in per_page},
            {p: page_identity(reads[p]) for p in per_page if p in reads})
        notes.extend(copy_notes)
        source["lines"] = len(kept)
        for line_no, (cells, region) in enumerate(kept, start=1):
            lines.append(RawLine(line_no=line_no, region=region, cells=cells))
        return lines, regions, errors, source, notes

    @staticmethod
    def _section_regions(reads: dict) -> list[RegionNode]:
        """One section box per region group (header/supplier/customer/money/payment/stamp/signature)."""
        out: list[RegionNode] = []
        for p in sorted(reads):
            groups: dict[str, list] = defaultdict(list)
            for it in reads[p].items:
                itype = str(it.get("type") or "other")
                label = str(it.get("label") or "")
                if itype == "table" or itype == "line":
                    kind = "table" if itype == "table" or label == "item_table" else None
                    if kind is None:
                        continue
                    groups["table"].append(it)
                    continue
                groups[itype].append(it)
            for group, items in groups.items():
                bbox = union_box([it["bbox"] for it in items])
                if not bbox:
                    continue
                kind = {"stamp": "stamp", "signature": "signature_box", "table": "table"}.get(group, "section")
                out.append(RegionNode(region_id=f"S{p}-{group}"[:31], page=p, kind=kind, label=group,
                                      text=" | ".join(str(it.get("text") or "") for it in items)[:400] or None,
                                      confidence=round(max(float(it.get("confidence") or 0) for it in items), 2),
                                      bbox=bbox))
        return out

    @staticmethod
    def _currency(ctx: _Ctx, invoice_pages: list) -> Optional[RawField]:
        for p in invoice_pages:
            text = ctx.layers.get(p, {}).get("text") or ""
            if _CURRENCY.search(text):
                return RawField(raw="THB", confidence=0.95, agreement=True, source="derived")
        return None


# --------------------------------------------------------------------------- pure helpers (unit tested)
def page_quality(items: list, layer_words: list) -> Optional[float]:
    """Share of readable text regions whose text the PDF text layer reproduces (measured OCR quality)."""
    checked = []
    for it in items:
        if str(it.get("type")) in ("signature", "stamp", "table"):
            continue
        inside = words_in_box(layer_words, it["bbox"])
        if not inside:
            continue
        checked.append(1.0 if same_text(it.get("text"), " ".join(w["text"] for w in inside)) else            0.0)
    return round(mean(checked), 3) if checked else None


def closest_pair(texts) -> tuple:
    """``(similarity, a, b)`` for the two most alike readings of one region - a comparison of what the
    readers saw, after the same folding that decides equality, so encoding noise is not counted as a
    difference of substance."""
    best = None
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            ratio = difflib.SequenceMatcher(None, _cmp(texts[i]), _cmp(texts[j])).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, texts[i], texts[j])
    return best or (0.0, None, None)


def consensus(vlm_text, layer_text, crop_text, vlm_conf: float, fuzzy: bool = False):
    """Majority of the independent readers (page VLM / PDF text layer / zoomed crop read).

    Returns ``(raw, confidence, agreement, source, null_reason)``.  Two agreeing readers -> trusted
    (0.96, three -> 0.98).  One reader only -> kept, ``agreement=False``, confidence <= 0.70.
    Three different readings -> the page read is kept as evidence, flagged ``CONFLICT_BETWEEN_SOURCES``.

    ``fuzzy`` is for free-text fields (names, addresses).  Digits are read the same way by every engine;
    Thai words are not - the DMS text layer is OCRmyPDF output with no Thai language data, so it spells
    "บริษัท อาปิโก ไฮเทค อยุธยา จำกัด" as "บ ร ษั ท อ า ปิ โก ..." and a zoomed re-read truncates the first
    syllable.  For those fields two readers count as agreeing when they are the same text apart from OCR
    noise, measured by sequence similarity; the trust level is deliberately below an exact agreement and the
    measured similarity is reported as evidence.  Money, identifiers and dates are never judged this way.
    """
    votes = [v for v in (vlm_text, layer_text, crop_text) if v and str(v).strip()]
    if not votes:
        return None, 0.0, False, "vlm", "NOT_PRESENT"
    tally = Counter(_key(v) for v in votes)
    top, count = tally.most_common(1)[0]
    winner = next(v for v in votes if _key(v) == top)
    if count >= 2:
        conf = 0.98 if count >= 3 else 0.96
        return winner, conf, True, "consensus", None
    if fuzzy and len(votes) >= 2:
        ratio, a, b = closest_pair(votes)
        if ratio >= TEXT_AGREEMENT_SIMILARITY:
            page_read = _key(vlm_text or "")
            chosen = a if _key(a) == page_read else (b if _key(b) == page_read else a)
            return chosen, TEXT_AGREEMENT_CONFIDENCE, True, "consensus", None
    if len(votes) == 1:
        return winner, round(min(float(vlm_conf or 0.6), 0.70), 2), False, \
            ("vlm" if _key(winner) == _key(vlm_text or "") else "ocr"), None
    return (vlm_text or winner), round(min(float(vlm_conf or 0.5), 0.55), 2), False, "vlm", \
        "CONFLICT_BETWEEN_SOURCES"


def _cell_text(cells: dict, name: str) -> str:
    cell = cells.get(name)
    return "" if cell is None else str(getattr(cell, "raw", None) or "")


def _row_signature(cells: dict) -> tuple:
    """The printed money of a row - what a photocopy of the same invoice reproduces exactly."""
    return tuple(_key((MONEY_RE.findall(thai_to_arabic(_cell_text(cells, c))) or [""])[-1]) or ""
                 for c in ("qty", "unit_price", "amount"))


#: printed evidence that says "this page is one specific invoice", used to prove a repeated page is a copy
IDENTITY_FIELDS = ("invoice_num", "grand_total")
TOKEN_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z/.\-_]*")


def _identity_key(name: str, text) -> Optional[str]:
    """Comparison key for one identity field - tolerant about the words printed around the value.

    This key decides only whether two pages are the same invoice printed twice; it is never shipped as a
    field value, so a document number still glued to its label ("เลขที่ NUMBER 0851392") may be compared by
    its last machine-readable token.  The values in the report come from the readers, not from here.
    """
    value, printed, rule = extract_value(name, text)
    if name in VALUE_TOKEN_FIELDS and rule == "whole_region" and printed:
        numbered = [t.rstrip("/.-_") for t in TOKEN_RE.findall(printed) if any(c.isdigit() for c in t)]
        numbered = [t for t in numbered if not DATE_RE.fullmatch(t)]      # "9290186640/ 2026/09/02" -> 9290186640
        if numbered:
            return numbered[0].lower()
    return _key(value) if value else None


def page_identity(read) -> tuple:
    """The invoice number and grand total *as printed on this page* - the fingerprint of one copy."""
    got: dict = {}
    for it in getattr(read, "items", []) or []:
        name = LABEL_TO_FIELD.get(str(it.get("label") or "").strip().lower())
        if name in IDENTITY_FIELDS and name not in got:
            key = _identity_key(name, it.get("text"))
            if key:
                got[name] = key
    return tuple(got.get(f) for f in IDENTITY_FIELDS)


def _row_signature(cells: dict) -> tuple:
    """The printed money of a row - what a photocopy of the same invoice reproduces exactly."""
    return tuple(_key((MONEY_RE.findall(thai_to_arabic(_cell_text(cells, c))) or [""])[-1]) or ""
                 for c in ("qty", "unit_price", "amount"))


#: how alike two printed descriptions must be before a page may count as a photocopy of another page
COPY_TEXT_SIMILARITY = 0.6


def _similar(a: str, b: str) -> bool:
    """The same item, allowing for the characters an OCR layer or a VLM read differently (spaces included)."""
    x, y = _cmp(a), _cmp(b)
    if not x and not y:
        return True
    return difflib.SequenceMatcher(None, x, y).ratio() >= COPY_TEXT_SIMILARITY


def drop_duplicate_copies(per_page: dict, page_types: dict, identity: dict | None = None) -> tuple[list, list]:
    """Return ``([(cells, region), ...], notes)`` with the **extra printed copies** of the invoice removed.

    These invoice PDFs are the whole printed set in one file - ``ต้นคบกณ ORIGINAL``,
    ``ลูกค้า CUSTOMER``, ``คู่คบกณ DUPLICATE`` - stacked page after page, each
    repeating the item table and the totals.  Read as continuation pages they multiply the line total, so
    V-03 fails on a document that is in perfect order.  A page is treated as a copy only when it is provably
    the same invoice printed again: same page type, same number of rows, the same printed qty / unit price /
    amount row by row, **and** the same invoice number printed on the page.  The printed grand total goes
    into the note as evidence but is not part of the test - the rows are what it adds up to, and one OCR
    confusion of ``0`` for ``8`` (measured on a copy of doc 20: 52,660.05 read as 52,660.85) must not turn a
    copy into a second page.  Item descriptions are not part of the test either - a copy measured on doc 19
    prints the same item as ``FL G05 95 x 220 x 250`` where the original prints
    ``MACHINED PLATE 95 x 220 x 250``.  A page that prints no invoice number is never dropped: without that
    fingerprint the repetition cannot be proven, so its rows are kept and the totals rule reports what it
    sees.
    """
    identity = identity or {}
    kept_pages: list = []
    notes: list = []
    out: list = []
    for page in sorted(per_page):
        rows = per_page[page]
        if not rows:
            continue
        # rows that print no qty/price/amount (a wrapped description line) do not take part in the comparison:
        # the same copy can come back with or without them depending on which pass read it (DMS-22 p1 vs p4/p5)
        sig = [x for x in (_row_signature(cells) for cells, _ in rows) if any(x)]
        stamp = identity.get(page)
        for first_page, first_rows in kept_pages:
            other = identity.get(first_page)
            if not stamp or not stamp[0] or not other or not other[0]:
                continue          # without a printed invoice number the repetition cannot be proven
            same_no = stamp[0] == other[0] or (
                len(stamp[0]) >= 6 and difflib.SequenceMatcher(None, stamp[0], other[0]).ratio() >= 0.85)
            if not same_no:
                continue          # this page does not carry the same printed invoice number
            first_sig = [x for x in (_row_signature(c) for c, _ in first_rows) if any(x)]
            if not sig or first_sig != sig:
                continue
            # identical money row by row: a different page type (the DELIVERY ORDER copy of the set) is still a copy
            # when there are at least two rows; a single row is too little evidence on its own
            if page_types.get(first_page) != page_types.get(page) and len(sig) < 2:
                continue
            notes.append({"page": page, "same_as_page": first_page, "rows": len(rows),
                          "printed": {"invoice_num": stamp[0], "grand_total": stamp[1]},
                          "rule": "same invoice number and the same qty / price / amount row by row -> printed copy"})
            break
        else:
            kept_pages.append((page, rows))
            out.extend(rows)
    return out, notes


QTY_WITH_UNIT = re.compile(r"^(\d[\d.,]*)\s+([A-Za-z\u0E01-\u0E4E][A-Za-z0-9\u0E01-\u0E4E./-]{0,11})$")


def split_qty_uom(cells: dict, notes: list, page: int, line_no: int) -> None:
    """Many Thai invoices print ``2 PCS`` inside the quantity column and have no unit column at all.

    The printed text is not a number, so the Standard's numeric qty would be dropped and V-01 would fail on
    every line.  The number and the unit are both on the page, so they are separated — and the merge is
    recorded in ``notes`` so the report shows which cells were split.  A page that already prints a unit
    column is left exactly as it is.
    """
    qty = cells.get("qty")
    if not qty or not qty.get("text") or (cells.get("uom") or {}).get("text"):
        return
    match = QTY_WITH_UNIT.match(qty["text"].strip())
    if not match:
        return
    number, unit = match.group(1), match.group(2)
    merged = qty["text"]
    cells["qty"] = {**qty, "text": number}
    cells["uom"] = {"text": unit, "bbox": qty.get("bbox"), "confidence": qty.get("confidence") or 0.0}
    notes.append({"page": page, "line_no": line_no, "printed_cell": merged, "qty": number, "uom": unit,
                  "column": "qty", "rule": "qty column prints number and unit together"})


def _same_printed_numbers(a: dict, b: dict) -> bool:
    cells_a, cells_b = a["cells"], b["cells"]
    seen = False
    for col in ("qty", "unit_price", "amount"):
        t1 = (cells_a.get(col) or {}).get("text")
        t2 = (cells_b.get(col) or {}).get("text")
        if t1 and t2:
            seen = True
            if not same_text(t1, t2):
                return False
    return seen


def _box_overlap(a, b) -> float:
    """Fraction of the smaller box covered by the other one (normalized [x, y, w, h] boxes)."""
    if not a or not b:
        return 0.0
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    smaller = min(a[2] * a[3], b[2] * b[3])
    return inter / smaller if smaller > 0 else 0.0


def merge_duplicate_rows(rows: list, page: int, tolerance: float = 0.5) -> tuple[list, list]:
    """One printed row must not become two rows.

    When a description wraps, a VLM answers the wrapped text line as a row *and* the whole item as another
    row, with the same qty/price/amount in the same place — which doubles the line total and fails V-03 on a
    correct invoice.  Rows that print the same numbers inside (almost) the same box are one row: keep the
    richest cells and record the merge in ``notes`` so the report shows it.
    """
    keep: list[dict] = []
    notes: list[dict] = []
    for row in rows:
        target = next((p for p in keep if _same_printed_numbers(p, row) and _box_overlap(p["bbox"], row["bbox"]) >= tolerance),
                      None)
        if target is None:
            keep.append(row)
            continue
        for col, cell in row["cells"].items():
            cur = target["cells"].get(col)
            text = (cell or {}).get("text")
            if not text:
                continue
            if not cur or not cur.get("text") or (col == "description" and len(text) > len(cur["text"])):
                target["cells"][col] = cell
        if target["bbox"] and row["bbox"]:
            target["bbox"] = union_box([target["bbox"], row["bbox"]])
        notes.append({"page": page, "line_no": row.get("line_no"), "merged_into": target.get("line_no"),
                      "printed_cell": (row["cells"].get("description") or {}).get("text"),
                      "rule": "same numbers printed in the same box -> one row"})
    return keep, notes


def parse_table_rows(raw: dict, img_w: int, img_h: int, page: int, words=None) -> dict:
    """Table answer -> rows with one normalized box per cell (coordinate mode detected once per page)."""
    rows_raw = raw.get("rows") if isinstance(raw, dict) else None
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError(f"table_rows: page {page} returned no rows list")
    all_boxes = [b for b in _iter_boxes(raw) if isinstance(b, (list, tuple)) and len(b) == 4]
    mode = choose_coord_mode(all_boxes, img_w, img_h, words, "auto")

    def conv(b):
        return xyxy_to_xywh(b, img_w, img_h, mode)

    columns = []
    for col in raw.get("columns") or []:
        if isinstance(col, dict) and isinstance(col.get("bbox_2d"), (list, tuple)):
            label = str(col.get("label") or "").strip().lower()
            if label:
                columns.append({"label": label, "bbox": conv(col["bbox_2d"])})
    out_rows = []
    notes: list[dict] = []
    for i, r in enumerate(rows_raw, start=1):
        if not isinstance(r, dict):
            continue
        cells = {}
        raw_cells = r.get("cells") if isinstance(r.get("cells"), dict) else {}
        for col, cell in raw_cells.items():
            if not isinstance(cell, dict):
                continue
            text = str(cell.get("text") or "").strip()
            b = cell.get("bbox_2d") or cell.get("bbox")
            bbox = conv(b) if isinstance(b, (list, tuple)) and len(b) == 4 else None
            if not text and not bbox:
                continue
            cells[str(col).strip().lower()] = {"text": text or None, "bbox": bbox,
                                               "confidence": float(cell.get("confidence") or 0)}
        if not cells:
            continue
        split_qty_uom(cells, notes, page, int(r["line_no"]) if isinstance(r.get("line_no"), (int, float)) else i)
        rb = r.get("bbox_2d") or r.get("bbox")
        row_box = conv(rb) if isinstance(rb, (list, tuple)) and len(rb) == 4 else None
        cell_boxes = [c["bbox"] for c in cells.values() if c["bbox"]]
        if row_box and cell_boxes:                       # never ship a row box that excludes its own cells
            row_box = union_box([row_box] + cell_boxes)
        row_box = row_box or union_box(cell_boxes)
        line_no = r.get("line_no")
        out_rows.append({"line_no": int(line_no) if isinstance(line_no, (int, float)) else i,
                         "bbox": row_box, "cells": cells, "order": i})
    out_rows.sort(key=lambda r: (round(r["bbox"][1], 3) if r["bbox"] else 0.0, r["order"]))
    out_rows, merge_notes = merge_duplicate_rows(out_rows, page)
    notes.extend(merge_notes)
    table_bbox = raw.get("table_bbox")
    table_bbox = conv(table_bbox) if isinstance(table_bbox, (list, tuple)) and len(table_bbox) == 4 else \
        union_box([r["bbox"] for r in out_rows if r["bbox"]])
    return {"rows": out_rows, "columns": columns, "table_bbox": table_bbox, "coord_mode": mode,
            "notes": notes}


def _iter_boxes(raw):
    if isinstance(raw, dict):
        for key in ("table_bbox",):
            if raw.get(key):
                yield raw[key]
        for col in raw.get("columns") or []:
            if isinstance(col, dict) and col.get("bbox_2d"):
                yield col["bbox_2d"]
        for r in raw.get("rows") or []:
            if not isinstance(r, dict):
                continue
            if r.get("bbox_2d"):
                yield r["bbox_2d"]
            for cell in (r.get("cells") or {}).values() if isinstance(r.get("cells"), dict) else []:
                if isinstance(cell, dict) and cell.get("bbox_2d"):
                    yield cell["bbox_2d"]


def rows_from_line_items(read: PageRead) -> list[dict]:
    """Fallback rows: the whole-row box from the page read, text in ``description`` only.

    Column values are *not* guessed from a row box — an unread cell stays null with ``NOT_PRESENT``.
    """
    out = []
    rows = [it for it in read.items if str(it.get("label") or "").strip().lower().startswith("line_")]
    rows.sort(key=lambda it: (round(it["bbox"][1], 3), it["bbox"][0]))
    for i, it in enumerate(rows, start=1):
        text = str(it.get("text") or "").strip()
        if not text:
            continue
        conf = float(it.get("confidence") or 0)
        parsed = cells_from_row_text(text)
        if not parsed and out and any(k != "description" for k in out[-1]["cells"]):
            # a printed row without qty/price/amount right under an item row is that item's wrapped description
            # ("( Project:AHD_AS ..., Task:07.2 - DFG0011022A )"), not an item of its own
            prev = out[-1]["cells"].get("description") or {"text": "", "bbox": it["bbox"], "confidence": conf}
            out[-1]["cells"]["description"] = {**prev, "text": (str(prev.get("text") or "") + " " + text).strip()}
            out[-1]["bbox"] = union_box([out[-1]["bbox"], it["bbox"]])
            continue
        cells = {"description": {"text": text, "bbox": it["bbox"], "confidence": conf}}
        if parsed:
            # each value is a printed token of the row; the row box (Qwen's) is used for every cell
            cells = {k: {"text": v, "bbox": it["bbox"], "confidence": conf} for k, v in parsed.items() if v}
        out.append({"line_no": i, "bbox": it["bbox"], "order": i, "cells": cells})
    return out


_NUM2 = r"\d[\d,]*\.\d{2}"
_ROW_TAIL = re.compile(rf"(?P<qty>\d[\d,]*(?:\.\d+)?)\s+(?P<uom>[A-Za-z\u0E01-\u0E4E][A-Za-z0-9\u0E01-\u0E4E./-]{{0,11}})\s+"
                       rf"(?P<money>{_NUM2}(?:\s+{_NUM2}){{1,2}})\s*$")
_ROW_TAIL_UOM_FIRST = re.compile(rf"(?P<uom>[A-Za-z\u0E01-\u0E4E][A-Za-z0-9\u0E01-\u0E4E./-]{{0,11}})\s+(?P<qty>\d+(?:\.\d+)?)\s+"
                                 rf"(?P<money>{_NUM2}(?:\s+{_NUM2}){{1,2}})\s*$")


def cells_from_row_text(text: str) -> Optional[dict]:
    """A printed item row -> {description, qty, uom, unit_price, amount}, or None when it does not end in them.

    Used when the table pass did not run for a page (DMS-22 pages 5+: every row came back description-only and
    produced 11 x 4 NOT_PRESENT cells).  Three trailing amounts (weight/price/amount or price/discount/amount) are
    resolved by the row's own arithmetic; nothing is guessed when the row does not parse.
    """
    from decimal import Decimal, InvalidOperation
    t = re.sub(r"\b(THB|BAHT)\b|฿|บาท", " ", str(text or ""), flags=re.I)
    t = re.sub(r"\s+", " ", thai_to_arabic(t)).strip()
    m = _ROW_TAIL.search(t) or _ROW_TAIL_UOM_FIRST.search(t)
    if not m:
        return None
    toks = m.group("money").split()
    try:
        q = Decimal(m.group("qty").replace(",", ""))
        vals = [Decimal(x.replace(",", "")) for x in toks]
    except InvalidOperation:
        return None
    if len(toks) == 2:
        price, amount = toks
    else:
        a, b, c = vals
        if abs(q * b - c) <= Decimal("0.01"):
            price = toks[1]
        elif abs(q * a - c) <= Decimal("0.01"):
            price = toks[0]
        else:
            price = toks[0] if b == 0 else toks[1]
        amount = toks[2]
    return {"description": t[:m.start()].strip() or None, "qty": m.group("qty"), "uom": m.group("uom"),
            "unit_price": price, "amount": amount}


def group_documents(reads: dict, invoice_pages: list) -> tuple[tuple, str]:
    """D1 = the invoice/tax-invoice pages; each following run of same-type pages becomes its own document."""
    docs: list[DocumentInfo] = []
    inv = sorted(invoice_pages)
    confs = [reads[p].type_confidence for p in inv if reads[p].type_confidence is not None]
    docs.append(DocumentInfo(document_id="D1", document_type="INVOICE", pages=tuple(inv),
                             confidence=round(mean(confs), 2) if confs else None))
    others = [p for p in sorted(reads) if p not in inv]
    run: list[int] = []
    for p in others + [None]:
        boundary = bool(run) and (p is None or p != run[-1] + 1 or reads[p].page_type != reads[run[-1]].page_type)
        if boundary:
            docs.append(DocumentInfo(document_id=f"D{len(docs) + 1}", document_type=reads[run[0]].page_type,
                                     pages=tuple(run), confidence=reads[run[0]].type_confidence))
            run = []
        if p is not None:
            run.append(p)
    return tuple(docs), "D1"


def element_boxes(ext: ExtractionResult) -> list[dict]:
    """Flat id/parent/bbox view of one extraction, for the parent-consistency gate."""
    out: list[dict] = [{"element_id": f"P{p.page_no}", "parent_id": None, "bbox": (0.0, 0.0, 1.0, 1.0)}
                       for p in ext.pages]
    did = ext.invoice_document_id
    for name, rf in ext.fields.items():
        if rf.region:
            out.append({"element_id": f"{did}-f-{name}", "parent_id": f"P{rf.region.page}", "bbox": rf.region.bbox})
    for ln in ext.lines:
        lid = f"{did}-L{ln.line_no}"
        if ln.region:
            out.append({"element_id": lid, "parent_id": f"P{ln.region.page}", "bbox": ln.region.bbox})
        for col, rf in ln.cells.items():
            if rf.region:
                out.append({"element_id": f"{lid}-{col}", "parent_id": lid if ln.region else
                            f"P{rf.region.page}", "bbox": rf.region.bbox})
    for rg in ext.regions:
        out.append({"element_id": rg.region_id, "parent_id": f"P{rg.page}", "bbox": rg.bbox})
    return out


# --------------------------------------------------------------------------- field choice / corroboration
_MONEY_FIELDS = ("sub_total", "vat", "grand_total")


def _money(v):
    from decimal import Decimal, InvalidOperation
    t = thai_to_arabic(str(v))
    m = re.findall(r"\d[\d,]*(?:\.\d+)?", t)            # "596.40 THB" -> 596.40
    if len(m) != 1:
        return None
    try:
        return Decimal(m[0].replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def pick_candidate(name: str, options: list, first_invoice):
    """Which of several regions labelled ``name`` is the field.

    Order: on the first invoice page, has the field's printed shape, highest stated confidence, earliest page.
    ``grand_total`` additionally prefers the largest well-shaped amount on that page: DMS-20 labels both
    "TOTAL / BAHT 49,215.00" and "GRAND TOTAL 52,660.05" grand_total and the first one failed V-03.
    """
    def key(c):
        page, it = c
        value = extract_value(name, it.get("text"))[0]
        return (page != first_invoice, not shape_ok(name, value), -float(it.get("confidence") or 0), page)
    ranked = sorted(options, key=key)
    page, it = ranked[0]
    if name == "grand_total":
        same = [(p, i) for p, i in ranked if p == page and shape_ok(name, extract_value(name, i.get("text"))[0])]
        if len(same) > 1:
            page, it = max(same, key=lambda c: _money(extract_value(name, c[1].get("text"))[0]) or 0)
    return page, it


def po_from_lines(fields: dict, reads: dict, invoice_pages: list, log: list, layers: Optional[dict] = None) -> None:
    """A PO number with the wrong shape (DMS-15: the customer code ``A002``) is replaced by the PO printed in the
    item rows (``40117545-975`` = PO 40117545 release 975) when exactly one such PO appears there."""
    cur = fields.get("po_number")
    if cur is not None and cur.raw and shape_ok("po_number", cur.raw):
        return
    found: dict = {}
    for p in invoice_pages:
        for it in reads[p].items if p in reads else []:
            label = str(it.get("label") or "").lower()
            if not (label.startswith("line_") or label in ("po_number", "invoice_ref", "item_table", "remark")):
                continue
            for m in PO_IN_TEXT.finditer(thai_to_arabic(str(it.get("text") or ""))):
                found.setdefault(m.group(1), (p, it, m.group(0)))
    if len(found) != 1:
        if cur is not None and found:
            log.append({"field": "po_number", "derived": None, "candidates": sorted(found)})
        return
    po, (p, it, printed) = next(iter(found.items()))
    # the same token in the text layer of that page is a second, independent reading
    layer_ok = any(re.sub(r"\D", "", str(w.get("text") or ""))[:8] == po and printed[:8] in str(w.get("text") or "")
                   for w in (layers.get(p, {}).get("words", []) if layers else []))
    fields["po_number"] = RawField(raw=printed, confidence=0.96 if layer_ok else 0.9, agreement=layer_ok,
                                   region=Region(page=p, bbox=it["bbox"]), source="derived", null_reason=None)
    log.append({"field": "po_number", "replaced": cur.raw if cur is not None else None, "derived": printed,
                "from": str(it.get("label")), "page": p, "text_layer_confirms": layer_ok,
                "rule": "the only 8-digit PO printed in the item rows"})


def corroborate(fields: dict, lines: list, uom_vocab: set) -> list:
    """Arithmetic and vocabulary as an independent reader.

    A cell the text layer could not confirm (it read ``50 PCS`` as ``OPCS``) is still trustworthy when the row's
    own arithmetic closes: qty x unit_price = amount to the satang.  Likewise sub_total / vat / grand_total when
    lines -> sub_total -> +VAT -> grand_total all close, and a unit when it is in the Standard's unit list.
    Only ever *raises* agreement; a reading that breaks the arithmetic is left exactly as it was, so V-02/V-03
    still report it.  Every upgrade is listed in ``extra.corroborations``.
    """
    from decimal import Decimal
    out: list = []
    lines_sum = Decimal(0)
    all_amounts = True
    for i, ln in enumerate(lines):
        c = dict(ln.cells)
        q, pr, am = (_money(c[k].raw) if c.get(k) and c[k].raw else None for k in ("qty", "unit_price", "amount"))
        if am is None:
            all_amounts = False
        else:
            lines_sum += am
        changed = []
        if None not in (q, pr, am) and abs(q * pr - am) <= Decimal("0.01"):
            for k in ("qty", "unit_price", "amount"):
                if not c[k].agreement:
                    c[k] = c[k].model_copy(update={"agreement": True, "confidence": max(c[k].confidence or 0, 0.95),
                                                   "null_reason": None})
                    changed.append(k)
        u = c.get("uom")
        if u is not None and u.raw and not u.agreement and str(u.raw).strip().upper().rstrip(".") in uom_vocab:
            c["uom"] = u.model_copy(update={"agreement": True, "confidence": max(u.confidence or 0, 0.9),
                                            "null_reason": None})
            changed.append("uom")
        if changed:
            lines[i] = ln.model_copy(update={"cells": c})
            out.append({"line_no": ln.line_no, "cells": changed,
                        "rule": "qty x unit_price = amount" if set(changed) - {"uom"} else "unit in Standard list"})
    sub, vat, grand = (_money(fields[k].raw) if fields.get(k) and fields[k].raw else None for k in _MONEY_FIELDS)
    if None not in (sub, vat, grand) and abs(sub + vat - grand) <= Decimal("0.01") and \
            abs(sub * Decimal("0.07") - vat) <= Decimal("1.00") and \
            (not lines or not all_amounts or abs(lines_sum - sub) <= Decimal("0.01")):
        changed = []
        for k in _MONEY_FIELDS:
            if not fields[k].agreement:
                fields[k] = fields[k].model_copy(update={"agreement": True, "confidence": max(fields[k].confidence or 0, 0.95),
                                                         "null_reason": None})
                changed.append(k)
        if changed:
            out.append({"fields": changed, "rule": "lines = sub_total, sub_total x 7% = vat, sub_total + vat = grand_total"})
    return out


def reconcile_grand_total(fields: dict, candidates: dict, log: list) -> None:
    """When sub_total + vat != grand_total, look for the printed grand total that does close the sum.

    DMS-20 page 1 prints "TOTAL / BAHT 49,215.00" and "GRAND TOTAL 52,660.05" next to each other; the region that
    was labelled grand_total held the first.  Any grand_total-labelled region (any page of the invoice) that prints
    an amount equal to sub_total + vat is taken instead - that amount is then confirmed by the arithmetic itself.
    """
    from decimal import Decimal
    sub, vat, grand = (fields.get(k) for k in _MONEY_FIELDS)
    if not (sub and vat and sub.raw and vat.raw):
        return
    s, v = _money(sub.raw), _money(vat.raw)
    g = _money(grand.raw) if grand and grand.raw else None
    if s is None or v is None or (g is not None and abs(s + v - g) <= Decimal("0.01")):
        return
    target = s + v
    for page, it in sorted(candidates.get("grand_total", []), key=lambda c: c[0]):
        arabic = thai_to_arabic(str(it.get("text") or ""))
        for m in MONEY_RE.finditer(arabic):
            val = str(it.get("text"))[m.start():m.end()]
            if shape_ok("grand_total", val) and _money(val) is not None and abs(_money(val) - target) <= Decimal("0.01"):
                fields["grand_total"] = RawField(raw=val, confidence=0.95, agreement=True,
                                                 region=Region(page=page, bbox=it["bbox"]), source="consensus")
                log.append({"field": "grand_total", "replaced": grand.raw if grand else None, "derived": val, "page": page,
                            "rule": "the printed amount that equals sub_total + vat"})
                return


def row_box_from_page(read, table_row_box):
    """The page-read ``line_N`` box that best overlaps a table row vertically (None when nothing overlaps >= 50 %)."""
    if not table_row_box or read is None:
        return None
    y0, y1 = table_row_box[1], table_row_box[1] + table_row_box[3]
    best, score = None, 0.0
    for it in read.items:
        if not str(it.get("label") or "").lower().startswith("line_") or not it.get("bbox"):
            continue
        b = it["bbox"]
        ov = min(y1, b[1] + b[3]) - max(y0, b[1])
        if ov <= 0:
            continue
        r = ov / max(1e-6, min(b[3], y1 - y0))
        if r > score:
            best, score = tuple(b), r
    return best if score >= 0.5 else None
