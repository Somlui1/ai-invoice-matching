"""Production perception (Qwen-VL on GB300): classify -> extract (pass A) -> crop re-read (pass B) -> consensus.

Produces ``ExtractionResult``.  Requires LiteLLM; not executed in the sandbox (use fixtures there).
"""
from __future__ import annotations

import base64
from decimal import Decimal

from ..adapters.llm.litellm_client import LiteLLMClient
from ..domain.contracts import DocumentInfo, ExtractionResult, PageInfo, RawField, RawLine, Region, SignatureObs
from .pdf_ingest import ingest_pdf

CLASSIFY = ("จำแนกประเภทหน้าเอกสาร: INVOICE, TAX_INVOICE, PO, OSP, DELIVERY_NOTE, SUPPORTING, UNKNOWN "
            'ตอบ JSON {"page_type": "...", "confidence": 0.0-1.0, "is_copy": bool}')
EXTRACT = (
    "สกัดข้อมูลทั้งหมดจากใบแจ้งหนี้ ห้ามเดาค่าที่อ่านไม่ได้ (ให้ null + null_reason) "
    "ทุกค่าต้องมี bbox [x,y,w,h] แบบ normalized 0-1 มุมบนซ้าย และ confidence. ตอบ JSON: "
    '{"fields":{"invoice_num":{"raw":..,"bbox":..,"confidence":..},...},'
    '"lines":[{"line_no":1,"bbox":..,"cells":{"description":{...},"qty":{...},"uom":{...},"unit_price":{...},"amount":{...}}}],'
    '"signatures":{"receiver":{"present":true,"confidence":..,"bbox":..},"deliverer":{...}},'
    '"extra":{"tables":[],"remarks":[],"stamps":[]}}')
REREAD = "อ่านค่าในภาพที่ครอปนี้ตามตัวอักษรเท่านั้น ห้ามเดา ตอบ JSON {\"raw\": \"...\", \"confidence\": 0-1}"
CRITICAL = ("invoice_num", "po_number", "customer_tax_id", "sub_total", "vat", "grand_total")


def _img(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _same(a, b) -> bool:
    try:
        return Decimal(str(a).replace(",", "")) == Decimal(str(b).replace(",", ""))
    except Exception:
        return str(a).replace(" ", "").upper() == str(b).replace(" ", "").upper()


class VlmExtractor:  # pragma: no cover - needs GB300
    def __init__(self, client: LiteLLMClient, model: str, votes: int = 3):
        self.c, self.model, self.votes = client, model, votes

    def run(self, pdf: bytes, package_id: str, dms_doc_id: str) -> ExtractionResult:
        import fitz
        sha, pages = ingest_pdf(pdf)
        infos = []
        for p in pages:
            votes = [self.c.chat_json(self.model, CLASSIFY, "", temperature=0.7, images=[_img(p.png)])
                     for _ in range(self.votes)]
            top = max({v["page_type"] for v in votes}, key=lambda t: sum(v["page_type"] == t for v in votes))
            conf = sum(v["page_type"] == top for v in votes) / self.votes
            infos.append(PageInfo(**{**p.info.model_dump(), "page_type": top if conf >= 0.66 else "UNKNOWN",
                                     "type_confidence": conf}))
        inv_pages = tuple(i.page_no for i in infos if i.page_type in ("INVOICE", "TAX_INVOICE")) or (1,)
        docs = (DocumentInfo(document_id="D1", document_type="INVOICE", pages=inv_pages),)
        a = self.c.chat_json(self.model, "", EXTRACT, images=[_img(pages[n - 1].png) for n in inv_pages])
        fields = {}
        with fitz.open(stream=pdf, filetype="pdf") as doc:
            for k, v in (a.get("fields") or {}).items():
                region = Region(page=v.get("page", inv_pages[0]), bbox=tuple(v["bbox"])) if v.get("bbox") else None
                agree = True
                if k in CRITICAL and region and v.get("raw") is not None:
                    pg = doc[region.page - 1]
                    x, y, w, h = region.bbox
                    clip = fitz.Rect(x * pg.rect.width, y * pg.rect.height, (x + w) * pg.rect.width,
                                     (y + h) * pg.rect.height) + (-6, -4, 6, 4)
                    b = self.c.chat_json(self.model, REREAD, "", images=[_img(pg.get_pixmap(dpi=400, clip=clip).tobytes("png"))])
                    agree = _same(v["raw"], b.get("raw"))
                fields[k] = RawField(raw=v.get("raw"), confidence=v.get("confidence"), agreement=agree, region=region,
                                     null_reason=v.get("null_reason"), source="consensus")
        lines = tuple(RawLine(line_no=l["line_no"], region=Region(page=l.get("page", inv_pages[0]), bbox=tuple(l["bbox"]))
                              if l.get("bbox") else None,
                              cells={k: RawField(raw=c.get("raw"), confidence=c.get("confidence"),
                                                 region=Region(page=l.get("page", inv_pages[0]), bbox=tuple(c["bbox"]))
                                                 if c.get("bbox") else None) for k, c in l["cells"].items()})
                      for l in a.get("lines", []))
        sigs = {k: SignatureObs(present=s.get("present"), confidence=s.get("confidence"),
                                region=Region(page=s.get("page", inv_pages[-1]), bbox=tuple(s["bbox"])) if s.get("bbox") else None)
                for k, s in (a.get("signatures") or {}).items() if k in ("receiver", "deliverer")}
        return ExtractionResult(package_id=package_id, dms_doc_id=dms_doc_id, file_sha256=sha, pages=tuple(infos),
                                documents=docs, invoice_document_id="D1", fields=fields, lines=lines,
                                signatures=sigs, extra=a.get("extra") or {},
                                extractor={"vlm": self.model, "prompt": "extract-v4", "consensus": "dual-read+crop"})
