"""ของจำเป็นเรื่อง PDF (PyMuPDF) ที่ portal ใช้ทั้งตอน render หน้าและตอนแปลงภาพเป็น PDF.

System A ใช้ ``fitz`` อยู่แล้ว (``system_a/perception/pdf_ingest.py``) จึงใช้ API ชุดเดียวกัน
"""
from __future__ import annotations

from typing import Tuple

import fitz  # PyMuPDF


def pdf_page_count(pdf: bytes) -> int:
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return len(doc)


def _page_rect(doc, page: int):
    if not 1 <= int(page) <= len(doc):
        raise ValueError(f"page {page} is not in a {len(doc)}-page PDF")
    return doc[int(page) - 1]


def pdf_page_size_px(pdf: bytes, page: int, *, dpi: int) -> Tuple[int, int]:
    """ขนาดหน้าเป็นพิกเซลที่ ``dpi`` เดียวกับที่ใช้ render — bbox (0-1) คำนวณบนตัวเลขชุดนี้"""
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        r = _page_rect(doc, page).rect
    return int(round(r.width * dpi / 72)), int(round(r.height * dpi / 72))


def pdf_page_image(pdf: bytes, page: int, *, dpi: int) -> bytes:
    """render หน้าของ PDF เป็น PNG ที่ ``dpi`` (หน้าจริงของ DMS ไม่ใช่ไฟล์ JPG ที่ cache ไว้ที่อื่น)"""
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        pm = _page_rect(doc, page).get_pixmap(dpi=dpi)
        return pm.tobytes("png")


def image_bytes_to_pdf(raw: bytes, *, dpi: int = 150) -> bytes:
    """Paperless เก็บบางเอกสารเป็นภาพ (image/jpeg) — ฝังเป็น PDF 1 หน้าเพื่อให้ pipeline อ่านได้
    ขนาดหน้าตั้งให้ 1 จุดบน PDF = 1 พิกเซลที่ ``dpi`` จึง render กลับได้ภาพเท่าต้นฉบับ"""
    probe = fitz.open(stream=raw)                          # fitz เปิด image/png/jpeg ได้โดยตรง
    w_px, h_px = probe[0].rect.width, probe[0].rect.height
    rot = probe[0].rotation
    probe.close()
    if rot:                                               # fitz นับความกว้าง/สูงรวม rotation แล้ว
        w_px, h_px = max(w_px, h_px), min(w_px, h_px)
    doc = fitz.open()
    page = doc.new_page(width=w_px * 72 / dpi, height=h_px * 72 / dpi)
    page.insert_image(page.rect, stream=raw)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
