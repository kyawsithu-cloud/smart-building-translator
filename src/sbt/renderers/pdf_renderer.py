"""Writes translations into a copy of a PDF.

Text pages: the original text of each translated paragraph is removed with a redaction (text only — images and
vector graphics stay), then the translation is laid out in the same rectangle, shrinking the font if needed.
Scanned pages: the text lines are covered with their own background colour and the translation drawn on top.
"""
from __future__ import annotations

import html
from collections import defaultdict
from pathlib import Path

import numpy as np
import pymupdf

from sbt import languages
from sbt.domain.models import DocumentModel, Issue, Segment, Severity
from sbt.pipeline.tags import split_spans
from sbt.renderers.fonts import WINDOWS_FONTS, for_language

LINE_HEIGHT = 1.15


def _css_style(style: dict[str, object], base: dict[str, object] | None = None) -> str:
    parts = []
    if base is None or style.get("bold") != base.get("bold"):
        parts.append(f"font-weight: {'bold' if style.get('bold') else 'normal'}")
    if base is None or style.get("italic") != base.get("italic"):
        parts.append(f"font-style: {'italic' if style.get('italic') else 'normal'}")
    if base is None or style.get("color") != base.get("color"):
        parts.append(f"color: {style.get('color', '#000000')}")
    if base is None or style.get("size") != base.get("size"):
        parts.append(f"font-size: {style.get('size', 10)}px")
    if base is None or style.get("serif") != base.get("serif"):
        parts.append(f"font-family: {'sbt-serif' if style.get('serif') else 'sbt-sans'}")
    return "; ".join(parts)


def target_prefix(prefix: str, latin_target: bool) -> str:
    """List marker for the output: OCR's Japanese bullet ・ cannot be drawn by Latin fonts (shows as a box),
    and '2.Title' needs a space in English."""
    if not prefix:
        return ""
    if latin_target:
        prefix = prefix.replace("\u30fb", "\u2022")
        if not prefix.endswith((" ", "\u00a0")):
            prefix += " "
    return prefix


def to_html(seg: Segment, translation: str, latin_target: bool = False) -> tuple[str, str]:
    """(html body, css for the paragraph) for a tagged translation."""
    styles: dict[str, dict[str, object]] = seg.geometry.get("styles", {})  # type: ignore[assignment]
    base = styles.get("None", {"size": 10, "color": "#000000"})
    body = []
    prefix = target_prefix(str(seg.geometry.get("prefix", "")), latin_target)
    if prefix:
        body.append(html.escape(prefix))
    for tid, text in split_spans(translation):
        escaped = html.escape(text).replace("\n", "<br/>")
        style = styles.get(str(tid)) if tid is not None else None
        body.append(f'<span style="{_css_style(style, base)}">{escaped}</span>' if style else escaped)
    align = seg.geometry.get("align", "left")
    css = f"* {{{_css_style(base)}; line-height: {LINE_HEIGHT}; text-align: {align}; margin: 0; padding: 0}}"
    return "".join(body), css


def available_rect(rect: pymupdf.Rect, page_rect: pymupdf.Rect, others: list[pymupdf.Rect],
                   boxes: list[pymupdf.Rect], column_right: float) -> pymupdf.Rect:
    """Where translated text may go: the original text box, grown right to the column edge and down by up to
    half its height (at least ~1 line), stopping before other text and drawn shapes, and staying inside any
    shape that contains the text (diagram boxes, callouts)."""
    line_h = rect.height if rect.height < 30 else 14
    out = pymupdf.Rect(rect.x0, rect.y0, max(rect.x1, column_right), rect.y1 + max(0.5 * rect.height, 1.3 * line_h))
    out.y1 = min(out.y1, page_rect.y1 - 18)
    for box in boxes:
        if box.contains(rect + (-1, -1, 1, 1)):                 # text sits inside this shape
            out.x1 = min(out.x1, box.x1 - 2)
            out.y1 = min(out.y1, box.y1 - 1)
    for o in others + [b for b in boxes if not b.contains(rect + (-1, -1, 1, 1))]:
        if o.intersects(rect):
            continue
        overlaps_x = o.x0 < out.x1 and o.x1 > rect.x0
        overlaps_y = o.y0 < out.y1 and o.y1 > rect.y0
        if overlaps_x and o.y0 >= rect.y1 - 0.5:
            out.y1 = min(out.y1, o.y0 - 1)
        if overlaps_y and o.x0 >= rect.x1 - 0.5 and o.y0 < rect.y1 and o.y1 > rect.y0:
            out.x1 = min(out.x1, o.x0 - 3)
    out.x1 = max(out.x1, rect.x1)
    out.y1 = max(out.y1, rect.y1)
    return out


def _background(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[float, float, float]:
    """Median colour of the pixels just around a rectangle (scanned pages)."""
    ring = pymupdf.Rect(rect.x0 - 3, rect.y0 - 3, rect.x1 + 3, rect.y1 + 3) & page.rect
    pix = page.get_pixmap(clip=ring, dpi=72, colorspace=pymupdf.csRGB, alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    border = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    med = np.median(border, axis=0)
    return tuple(float(c) / 255 for c in med)  # type: ignore[return-value]


class PdfRenderer:
    file_types = frozenset({"pdf"})

    def __init__(self, source_lang: str, target_lang: str, min_font_scale: float = 0.8) -> None:
        self.source_lang = languages.get(source_lang)
        self.lang = languages.get(target_lang)
        self.min_font_scale = min_font_scale
        self.fonts = for_language(target_lang)

    def render(self, model: DocumentModel, output_path: Path) -> list[Issue]:
        if Path(output_path).resolve() == Path(model.source_path).resolve():
            raise ValueError("Refusing to overwrite the original document")
        doc = pymupdf.open(model.source_path)
        if doc.needs_pass:
            doc.authenticate("")
        archive = pymupdf.Archive(str(WINDOWS_FONTS))
        font_css = self.fonts.css()
        by_page: dict[int, list[Segment]] = defaultdict(list)
        for s in model.segments:
            if s.translation is not None and s.translation != s.source:
                by_page[int(s.geometry["page"])].append(s)  # type: ignore[call-overload]

        all_by_page: dict[int, list[pymupdf.Rect]] = defaultdict(list)
        for s in model.segments:
            all_by_page[int(s.geometry["page"])].append(pymupdf.Rect(s.geometry["rect"]))  # type: ignore[arg-type,call-overload]

        issues: list[Issue] = []
        for pno, segs in sorted(by_page.items()):
            page = doc[pno]
            boxes = [pymupdf.Rect(d["rect"]) for d in page.get_drawings()
                     if pymupdf.Rect(d["rect"]).get_area() < 0.5 * page.rect.get_area()]
            spaces = {}
            for s in segs:
                rect = pymupdf.Rect(s.geometry["rect"])  # type: ignore[arg-type]
                if s.geometry.get("cell"):
                    cell = pymupdf.Rect(s.geometry["cell"])  # type: ignore[arg-type]
                    spaces[s.id] = pymupdf.Rect(rect.x0, rect.y0, cell.x1 - 3, cell.y1 - 1)
                    continue
                same_column = [o.x1 for o in all_by_page[pno] if abs(o.x0 - rect.x0) < 30]
                others = [o for o in all_by_page[pno] if o != rect]
                spaces[s.id] = available_rect(rect, page.rect, others, boxes, max(same_column, default=rect.x1))
            text_segs = [s for s in segs if not s.geometry.get("ocr")]
            for s in text_segs:
                for r in s.geometry["line_rects"]:  # type: ignore[union-attr]
                    lr = pymupdf.Rect(r)
                    # vertically inset so neighbouring lines (whose boxes touch this one) are never clipped
                    page.add_redact_annot(lr + (0, lr.height * 0.2, 0, -lr.height * 0.2), fill=False)
            if text_segs:
                page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                                      graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                                      text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            for s in segs:
                rect = spaces[s.id]
                if s.geometry.get("ocr"):
                    for r in s.geometry["line_rects"]:  # type: ignore[union-attr]
                        lr = pymupdf.Rect(r)
                        page.draw_rect(lr + (-1, -1, 1, 1), color=None, fill=_background(page, lr), overlay=True)
                body, css = to_html(s, s.translation or "", self.lang.code in ("en", "de", "fr", "es"))
                spare, scale = page.insert_htmlbox(rect, body, css=font_css + "\n" + css, archive=archive,
                                                   scale_low=0)
                issues.extend(self._fit_issue(s, scale, spare))
        doc.subset_fonts()        # embed only the characters used: a full Japanese font is 10+ MB
        doc.save(str(output_path), garbage=3, deflate=True)
        doc.close()
        return issues

    def _fit_issue(self, s: Segment, scale: float, spare: float) -> list[Issue]:
        if spare < 0:
            return [Issue("overflow", Severity.WARNING, s.id, f"page {s.container}: text could not be placed")]
        if scale < self.min_font_scale - 1e-6:
            return [Issue("overflow", Severity.WARNING, s.id,
                          f"page {s.container}: text shrunk to {int(scale * 100)}% to fit its box")]
        if scale < 0.999:
            return [Issue("font_reduced", Severity.INFO, s.id,
                          f"page {s.container}: font reduced to {int(scale * 100)}% to fit")]
        return []

