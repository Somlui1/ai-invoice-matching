"""แหล่งเอกสารของ portal: ของจริงจาก **Paperless (DMS)**.

โหมดเดิมของ portal อ่านจาก batch report (``batch.py``) ซึ่งต้องรัน OCR มาก่อน — โหมดนั้นยังอยู่
โมดูลนี้ทำให้ portal แสดงรายการเอกสารจาก Paperless ได้โดยตรง แล้วให้ ``LivePerception`` อ่านไฟล์
ของเอกสารนั้นผ่าน ``system_a.perception.vision_pipeline.VisionPipeline`` (โค้ด System A ล้วน)

สิ่งที่คลาสนี้ทำ
  * list เอกสาร (limit / tag) แล้วเก็บเป็น ``BatchDoc`` ให้ UI ฝั่งซ้าย
  * โหลดไฟล์ของแต่ละเอกสาร (cache ใน memory) และแปลงไฟล์ภาพเป็น PDF ก่อนเสมอ
  * render แต่ละหน้าเป็น PNG ที่ DPI ที่ระบุ เพื่อ overlay bbox ที่ System A คืนมา
  * นับหน้า/ขนาดหน้าจริงจาก PDF ไม่ใช่จากไฟล์ JPG ที่ cache ไว้ที่อื่น

ใช้ ``BatchDoc`` / ``BatchPage`` ของ ``batch.py`` เป็นโครงข้อมูลร่วมกัน จึงไม่มีโค้ดฝั่ง service/UI
ที่ต้องแยกว่ากำลังดู batch หรือดู Paperless และไม่มีการเขียนผลที่ประมวลแล้วลงดิสก์ — cache
มีไว้กันโหลดซ้ำในกระบวนการเดียวเท่านั้น
"""
from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import List, Optional, Sequence, Tuple

from .batch import A4_PX, BatchDoc, BatchError, BatchPage, DEFAULT_COLORS
from .pdfkit import image_bytes_to_pdf, pdf_page_count, pdf_page_image, pdf_page_size_px

log = logging.getLogger("webapp.paperless")


class PaperlessSource:
    """เอกสารจาก Paperless — ใช้ API เดิมของ ``system_a.adapters.paperless.reader`` (GET เท่านั้น)"""

    kind = "paperless"
    owns_pdf = True                                     # the file only exists in the DMS: LivePerception asks us
    root: Optional[object] = None                       # ไม่มีโฟลเดอร์ให้อ่านแบบ StaticFiles

    def __init__(self, reader, *, limit: int = 200, tags: Sequence[str] = (), render_dpi: int = 150,
                 cache_docs: int = 8, cache_pages: int = 80) -> None:
        if limit < 1:
            raise BatchError("PAPERLESS_LIMIT must be >= 1")
        self.reader = reader
        self.limit = int(limit)
        self.tags = [str(t).strip() for t in (tags or []) if str(t).strip()]
        self.render_dpi = int(render_dpi)
        self.colors = dict(DEFAULT_COLORS)
        self.docs: List[BatchDoc] = []
        self.by_id: dict = {}
        self.last_count: Optional[int] = None
        self.tag_ids: List[int] = []
        self.unmatched_tags: List[str] = []
        self.list_error: Optional[str] = None
        self._lock = threading.Lock()
        self._pdf: "OrderedDict[int, Tuple[bytes, str]]" = OrderedDict()
        self._img: "OrderedDict[tuple, Tuple[bytes, str]]" = OrderedDict()
        self._dl: dict = {}                                 # doc_id -> lock: UI เรียกทุกหน้าพร้อมกันตอนเปิดเอกสาร
                                                            # จะได้ไม่ดาวน์โหลดไฟล์เดียวกันซ้ำ
        self._cache_docs, self._cache_pages = cache_docs, cache_pages

    def _dl_lock(self, key: int) -> threading.Lock:
        with self._lock:
            return self._dl.setdefault(key, threading.Lock())

    # ------------------------------------------------------------------ listing
    @property
    def base_url(self) -> str:
        return str(getattr(self.reader, "base", "") or getattr(self.reader, "base_url", "") or "")

    def _doc_url(self, doc_id: int) -> str:
        return f"{self.base_url.rstrip('/')}/documents/{int(doc_id)}/"

    def _as_ref(self, d) -> BatchDoc:
        """``system_a`` PaperlessDoc -> BatchDoc ที่ service/UI ใช้งานได้ทันที"""
        pages = int(d.page_count or 0)
        return BatchDoc(id=int(d.doc_id), title=str(d.title or d.file_name or f"DMS-{d.doc_id}"),
                        ptype=str(d.document_type or "").strip().lower().replace(" ", "_") or d.file_class or "other",
                        pages_total=pages, pages=[BatchPage(p) for p in range(1, pages + 1)],
                        created=str(d.created or ""), correspondent=str(d.correspondent or ""),
                        mime=str(d.mime_type or ""), file_class=d.file_class, dms_url=self._doc_url(d.doc_id))

    def refresh(self) -> "PaperlessSource":
        """ดึงรายการเอกสารจาก DMS — ถ้า DMS ล้ม ให้คงรายการเดิมไว้แล้วส่ง error กลับไปบอกผู้ใช้"""
        try:
            wanted = self.reader.tag_ids_for(self.tags) if self.tags else []
            self.tag_ids = [int(i) for i, _ in wanted]
            self.unmatched_tags = [t for t in self.tags
                                   if t.casefold() not in {n.casefold() for _, n in wanted}]
            found = {d.id: d for d in self.docs}
            docs = []
            for raw in self.reader.list_documents(tag_ids=self.tag_ids or None, limit=self.limit):
                d = self._as_ref(raw)
                old = found.get(d.id)
                if old is not None and len(old.pages) > len(d.pages):   # จำนวนที่รู้จาก PDF แล้วแม่นกว่า
                    d, d.pages_total = old, len(old.pages)
                docs.append(d)
            self.docs, self.by_id = docs, {d.id: d for d in docs}
            self.last_count = getattr(self.reader, "last_count", None)
            self.list_error = None
        except Exception as e:                            # any transport/shape failure: report, keep the old list
            self.list_error = f"อ่านรายการจาก Paperless ไม่สำเร็จ: {type(e).__name__}: {e}"[:300]
            log.warning("%s", self.list_error)
        return self

    def get(self, doc_id: int) -> BatchDoc:
        key = int(doc_id)
        if key in self.by_id:
            return self.by_id[key]
        try:                                              # เอกสารนอกหน้า list ก็เปิดตรงๆ ได้
            d = self._as_ref(self.reader.document(key))
        except Exception:
            raise KeyError(f"unknown document {doc_id}") from None
        self.by_id[key] = d
        return d

    # ---------------------------------------------------------------------- pdf
    def ensure(self, doc_id: int) -> BatchDoc:
        """ดาวน์โหลดไฟล์ (ถ้ายังไม่โหลด) แล้วแก้จำนวนหน้าให้ตรงกับ PDF จริง — ใช้ตอนเปิดเอกสาร"""
        self.pdf_bytes(int(doc_id))
        return self.get(int(doc_id))

    def pdf_bytes(self, doc_id: int) -> Tuple[bytes, str]:
        """``(ไฟล์ PDF, ที่มา)`` — ดึงจาก DMS ครั้งเดียวต่อเอกสาร แล้วเก็บไว้ใน memory ชั่วคราว"""
        key = int(doc_id)
        with self._lock:
            hit = self._pdf.get(key)
            if hit is not None:
                self._pdf.move_to_end(key)
                return hit
        with self._dl_lock(key):                    # คำขอหลายหน้าของเอกสารเดียวกันใช้การดาวน์โหลดครั้งเดียว
            with self._lock:
                hit = self._pdf.get(key)
            if hit is not None:
                return hit
            raw = self.reader.download(key)             # PaperlessError / httpx error = ส่งขึ้นให้ service บันทึก
            if not raw:
                raise BatchError(f"เอกสาร #{key} ดาวน์โหลดจาก Paperless ได้ไฟล์ว่างเปล่า")
            if raw[:4] == b"%PDF":
                origin = "dms:pdf"
            else:                                       # DMS เก็บบางเอกสารเป็นภาพ: แปลงเป็น PDF ก่อนเสมอ
                raw, origin = image_bytes_to_pdf(raw, dpi=self.render_dpi), "dms:image->pdf"
            d = self.by_id.get(key)
            if d is not None:
                n = pdf_page_count(raw)
                if n and len(d.pages) != n:
                    d.pages = [BatchPage(p) for p in range(1, n + 1)]
                    d.pages_total = n
            with self._lock:
                self._pdf[key] = (raw, origin)
                while len(self._pdf) > self._cache_docs:
                    self._pdf.popitem(last=False)
            return raw, origin

    # -------------------------------------------------------------------- pages
    def page_image(self, doc_id: int, page: int) -> Optional[Tuple[bytes, str]]:
        key = (int(doc_id), int(page))
        with self._lock:
            hit = self._img.get(key)
            if hit is not None:
                self._img.move_to_end(key)
                return hit
        pdf, _origin = self.pdf_bytes(doc_id)
        try:
            png = pdf_page_image(pdf, page, dpi=self.render_dpi)
        except ValueError:                                #หน้าเกินจำนวนหน้าจริงของ PDF
            return None
        with self._lock:
            self._img[key] = (png, "image/png")
            while len(self._img) > self._cache_pages:
                self._img.popitem(last=False)
        return png, "image/png"

    def page_size_px(self, doc_id: int, page: int) -> Tuple[int, int]:
        try:
            pdf, _ = self.pdf_bytes(doc_id)
            return pdf_page_size_px(pdf, page, dpi=self.render_dpi)
        except Exception:
            return A4_PX

    # ----------------------------------------------------------------- plumbing
    def viewer_url(self, doc_id: int) -> Optional[str]:
        return self._doc_url(doc_id)

    def health(self) -> dict:
        return self.reader.health()

    def stats(self) -> dict:
        return {"source": self.kind, "documents": len(self.docs), "pages": sum(d.pages_total for d in self.docs),
                "dms_total": self.last_count, "render_dpi": self.render_dpi, "limit": self.limit,
                "tags": self.tag_ids, "unmatched_tags": self.unmatched_tags, "list_error": self.list_error,
                "pdfs_cached": len(self._pdf), "pages_cached": len(self._img)}
