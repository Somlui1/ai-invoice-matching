"""Perception = how a batch document becomes an ``aiva.extraction/2.0`` extraction.

* ``ReplayPerception`` - reuse the OCR items already in the batch report (no GPU).  See ``extraction.py``.
* ``LivePerception``   - run System A's ``VisionPipeline`` (Qwen-VL via LiteLLM) on the document's PDF.  When no
  PDF exists, one is built from the page images of the batch, so the same pipeline can still run.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Protocol

from .batch import BatchSource
from .extraction import build_replay_extraction


class PerceptionError(RuntimeError):
    pass


class Perception(Protocol):
    name: str

    def extract(self, doc_id: int) -> dict: ...


class ReplayPerception:
    name = "replay"

    def __init__(self, batch: BatchSource, confidence: float = 0.97, assume_agreement: bool = True):
        self.batch, self.confidence, self.assume = batch, confidence, assume_agreement

    def extract(self, doc_id: int) -> dict:
        doc = self.batch.get(doc_id)
        sizes = {p.page: self.batch.page_size_px(doc.id, p.page) for p in doc.pages}
        try:
            return build_replay_extraction(doc, sizes, confidence=self.confidence, assume_agreement=self.assume)
        except Exception as e:
            raise PerceptionError(f"replay extraction failed for #{doc_id}: {type(e).__name__}: {e}") from e


def images_to_pdf(images: list[Path], dpi: int = 150) -> bytes:
    """One PDF page per image (page size = image size at ``dpi``).  Used when the batch has no PDF."""
    import fitz
    pdf = fitz.open()
    try:
        for img in images:
            pix = fitz.Pixmap(str(img))                    # pixel size, whatever DPI the file claims
            page = pdf.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
            page.insert_image(page.rect, filename=str(img))
        return pdf.tobytes()
    finally:
        pdf.close()


class LivePerception:
    name = "live"

    def __init__(self, batch: BatchSource, pdf_dir: Optional[Path], cache_dir: Path, pipeline=None):
        self.batch, self.pdf_dir, self.cache = batch, pdf_dir, Path(cache_dir)
        self._pipeline = pipeline                      # injectable (tests); built lazily from System A settings

    def pipeline(self):
        if self._pipeline is None:
            from system_a.container import Settings, build_perception
            self._pipeline = build_perception(Settings())
        return self._pipeline

    def pdf_bytes(self, doc_id: int) -> tuple[bytes, str]:
        """``(pdf bytes, origin)`` - the real PDF if there is one, else one built from the page images."""
        if getattr(self.batch, "owns_pdf", False):            # the file lives in Paperless: ask the source
            try:
                return self.batch.pdf_bytes(doc_id)
            except Exception as e:
                raise PerceptionError(f"#{doc_id}: cannot read the file from Paperless: {e}") from e
        found = self.batch.pdf_path(doc_id, self.pdf_dir)
        if found is not None:
            return found.read_bytes(), f"pdf:{found.name}"
        doc = self.batch.get(doc_id)
        imgs = [self.batch.image_path(doc.id, p.page) for p in doc.pages]
        if not imgs or any(i is None for i in imgs):
            raise PerceptionError(f"#{doc_id}: no PDF and the page images are missing - nothing to read")
        self.cache.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256("|".join(f"{i}:{i.stat().st_mtime_ns}" for i in imgs).encode()).hexdigest()[:16]
        out = self.cache / f"doc_{doc_id}_{key}.pdf"
        if not out.is_file():
            out.write_bytes(images_to_pdf(imgs))
        return out.read_bytes(), "images->pdf"

    def extract(self, doc_id: int) -> dict:
        pdf, origin = self.pdf_bytes(doc_id)
        try:
            ext = self.pipeline().extract(pdf, package_id=f"DMS-{doc_id}", dms_doc_id=str(doc_id))
        except Exception as e:
            raise PerceptionError(f"perception failed for #{doc_id}: {type(e).__name__}: {e}") from e
        out = ext.model_dump(mode="json")
        out.setdefault("extra", {})["live"] = {"input": origin, "pipeline": out.get("extractor", {}).get("pipeline")}
        return out


def build_perception_for(settings, batch: BatchSource) -> Perception:
    if settings.perception == "live":
        return LivePerception(batch, settings.pdf_dir, settings.data_dir / "pdf")
    return ReplayPerception(batch, settings.replay_confidence, settings.replay_assume_agreement)
