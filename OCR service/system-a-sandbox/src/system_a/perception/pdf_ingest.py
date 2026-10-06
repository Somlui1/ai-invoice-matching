"""STEP ingest: sha256, page geometry, rotation, rendering (PyMuPDF).  Temp data stays in memory."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import fitz  # PyMuPDF

from ..domain.contracts import PageInfo


@dataclass(frozen=True)
class RenderedPage:
    info: PageInfo
    png: bytes


def ingest_pdf(data: bytes, dpi: int = 300, render: bool = True) -> tuple[str, list[RenderedPage]]:
    sha = "sha256:" + hashlib.sha256(data).hexdigest()
    out = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for i, page in enumerate(pdf, start=1):
            info = PageInfo(page_no=i, width_pt=round(page.rect.width, 2), height_pt=round(page.rect.height, 2),
                            rotation=page.rotation, render_dpi=dpi)
            png = page.get_pixmap(dpi=dpi).tobytes("png") if render else b""
            out.append(RenderedPage(info, png))
    return sha, out


def _norm_box(x0: float, y0: float, x1: float, y1: float, w: float, h: float) -> tuple:
    """PDF-point box -> normalized ``[x, y, w, h]`` clamped to [0,1].

    Text-layer glyphs can hang a fraction of a point outside ``page.rect`` (accent marks above the top
    edge), which used to publish ``y = -0.0004``.  AC-08 requires every bbox in range, and a box with no
    size cannot be highlighted, so the clamp keeps a minimum positive extent.
    """
    W, H = max(float(w), 1e-6), max(float(h), 1e-6)
    x = min(max(float(x0) / W, 0.0), 1.0)
    y = min(max(float(y0) / H, 0.0), 1.0)
    bw = min(max((float(x1) - float(x0)) / W, 0.0), 1.0 - x)
    bh = min(max((float(y1) - float(y0)) / H, 0.0), 1.0 - y)
    return (round(x, 4), round(y, 4), round(max(bw, 0.0005), 4), round(max(bh, 0.0005), 4))


def page_text_and_words(data: bytes) -> list[dict]:
    """One pass over the PDF text layer: per page text plus normalized word boxes.

    Coordinates are normalized against ``page.rect`` (which already includes ``/Rotate``), so they line up
    with the rendered image.  Pages that are pure scans return an empty text/word list — that is recorded
    (``text_layer_chars``) rather than treated as "no text exists".
    """
    out: list[dict] = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for pno, page in enumerate(pdf, start=1):
            W, H = page.rect.width, page.rect.height
            words = [{"word_id": f"p{pno}-w{j:04d}", "page": pno, "text": txt,
                      "bbox": _norm_box(x0, y0, x1, y1, W, H)}
                     for j, (x0, y0, x1, y1, txt, *_r) in enumerate(page.get_text("words"))]
            out.append({"page": pno, "text": page.get_text(), "text_layer_chars": len(page.get_text().strip()),
                        "words": words})
    return out


def crop_png(data: bytes, page_no: int, rect_pt: tuple[float, float, float, float], dpi: int = 300,
             pad_pt: float = 2.0) -> bytes:
    """Zoomed crop of one box (PDF points, rotation-aware page space) as PNG bytes — the crop re-read pass."""
    with fitz.open(stream=data, filetype="pdf") as pdf:
        page = pdf[page_no - 1]
        x0, y0, x1, y1 = rect_pt
        if x1 <= x0 or y1 <= y0:                      # a zero-size box is a bad box, not a tiny crop
            return b""
        clip = fitz.Rect(max(0, x0 - pad_pt), max(0, y0 - pad_pt),
                         min(page.rect.width, x1 + pad_pt), min(page.rect.height, y1 + pad_pt))
        if clip.is_empty or clip.width <= 0 or clip.height <= 0:
            return b""
        return page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip).tobytes("png")


def words_from_text_layer(data: bytes, document_id: str) -> list[dict]:
    """Word boxes from the PDF text layer (digital PDFs).  Scanned pages need OCR (vlm_extractor)."""
    words = []
    with fitz.open(stream=data, filetype="pdf") as pdf:
        for pno, page in enumerate(pdf, start=1):
            W, H = page.rect.width, page.rect.height
            for j, (x0, y0, x1, y1, txt, *_r) in enumerate(page.get_text("words")):
                words.append({"word_id": f"{document_id}-p{pno}-w{j:04d}", "page": pno, "text": txt,
                              "bbox": _norm_box(x0, y0, x1, y1, W, H), "confidence": 1.0})
    return words


def pdf_from_image(data: bytes, mime: str = "image/jpeg") -> bytes:
    """Wrap a single image (a DMS document stored as JPEG/PNG/TIFF) into an in-memory PDF.

    Nothing is written to disk or back to the DMS; the bytes only exist so the rest of perception,
    which is PDF-native, can render and read the page.

    The image is *inserted*, never opened through PyMuPDF's image loader: when Tesseract is installed
    that loader silently OCRs the picture, and the local build has no Thai language data, so it would
    inject a bad text layer that perception would then trust as a second reader.  A wrapped image
    therefore has no text layer, which is the truth and is reported as such.
    Returns ``b""`` when the bytes are not a decodable image.
    """
    try:
        import io

        from PIL import Image
        with Image.open(io.BytesIO(data)) as probe:      # verify() rejects truncated / non-image bytes
            probe.verify()
        with Image.open(io.BytesIO(data)) as probe:
            w, h = probe.size
        if not w or not h:
            return b""
        out = fitz.open()
        page = out.new_page(width=float(w), height=float(h))     # 1 px = 1 pt: geometry stays honest
        page.insert_image(page.rect, stream=data)
        pdf = out.tobytes(deflate=True)
        out.close()
        return pdf
    except Exception:
        return b""


def is_pdf(data: bytes) -> bool:
    """Sniff the content, because the DMS serves the OCR'd *archive* version of an image upload —
    so the API's ``mime_type`` (``image/jpeg``) and the bytes we get back (``%PDF``) can disagree."""
    return str(data[:5], "latin-1", "replace").startswith("%PDF")
