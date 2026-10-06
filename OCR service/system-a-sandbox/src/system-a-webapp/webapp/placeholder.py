"""A stand-in page image, drawn from the OCR items, for batches whose page JPGs are not on disk.

It is an SVG, so the browser renders Thai text with its own fonts.  Boxes are positioned from the same
``bbox_norm`` the overlay uses, which makes the overlay line up with the text by construction.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from .batch import A4_PX, BatchPage


def page_svg(page: BatchPage, note: str = "") -> str:
    W, H = A4_PX
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           f'<rect width="{W}" height="{H}" fill="#fff"/>',
           '<g font-family="Tahoma,Arial,sans-serif" fill="#333">']
    if note:
        out.append(f'<text x="8" y="{H - 8}" font-size="13" fill="#b00">{escape(note)}</text>')
    for it in page.kept:
        b = it.get("bbox_norm")
        if not b:
            continue
        x, y, w, h = b[0] * W, b[1] * H, b[2] * W, b[3] * H
        if it.get("type") == "signature" or it.get("label") == "handwriting":
            out.append(f'<path d="M{x + w * .1:.0f} {y + h * .7:.0f} C{x + w * .3:.0f} {y:.0f} {x + w * .4:.0f} {y + h:.0f} '
                       f'{x + w * .55:.0f} {y + h * .4:.0f} S{x + w * .8:.0f} {y + h * .9:.0f} {x + w * .9:.0f} {y + h * .3:.0f}" '
                       f'stroke="#2a3f9a" fill="none" stroke-width="3"/>')
            continue
        if it.get("type") == "stamp":
            out.append(f'<ellipse cx="{x + w / 2:.0f}" cy="{y + h / 2:.0f}" rx="{w / 2:.0f}" ry="{h / 2:.0f}" '
                       f'stroke="#6a6aa8" fill="none" stroke-width="3"/>')
            continue
        text = " ".join(str(it.get("text") or "").split())
        if not text:
            continue
        lines_n, fs, cpl = 1, 12.0, 10.0
        for lines_n in range(1, 9):
            fs = min(h / lines_n / 1.15, 34.0)
            cpl = max(4.0, w / (max(fs, 6.0) * 0.55))
            if len(text) <= cpl * lines_n:
                break
        fs = max(fs, 8.0)
        rows, cur = [], ""
        for word in text.split(" "):
            while len(word) > cpl:
                if cur:
                    rows.append(cur)
                    cur = ""
                rows.append(word[:int(cpl)])
                word = word[int(cpl):]
            if cur and len(cur) + 1 + len(word) > cpl:
                rows.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            rows.append(cur)
        for k, row in enumerate(rows[:max(1, int(h // (fs * 1.1)))]):
            fit = f' textLength="{w:.0f}" lengthAdjust="spacingAndGlyphs"' if len(row) * fs * 0.55 > w else ""
            out.append(f'<text x="{x:.1f}" y="{y + fs * (k + 1) * 1.08:.1f}" font-size="{fs:.1f}"{fit}>{escape(row)}</text>')
    out.append("</g></svg>")
    return "".join(out)
