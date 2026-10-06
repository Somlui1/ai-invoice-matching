"""What the PDF text layer can and cannot vote on.

The text layer of a DMS document is OCRmyPDF/Tesseract output produced without Thai language data: it spells
Thai as isolated glyphs (``ษั ท อ ไป โก ไฮ เท ค``).  Such a reading is not a second opinion on a Thai value, so it
must abstain instead of counting as a reader that disagrees.  Boxes are never taken from the layer.
"""
from __future__ import annotations

import re

THAI = re.compile(r"[\u0E00-\u0E7F]")


def thai_fragment_ratio(text: str) -> float:
    """Share of whitespace tokens that are 1-2 Thai characters."""
    toks = str(text or "").split()
    if not toks:
        return 0.0
    return sum(1 for t in toks if THAI.search(t) and len(t) <= 2) / len(toks)


def layer_unreliable(text) -> bool:
    return bool(text) and thai_fragment_ratio(text) >= 0.35
