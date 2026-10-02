"""PDF → segments with layout geometry.

Per page:
  scanned (almost no text layer, mostly image)  → OCR lines grouped into paragraphs
  text page → tables (cell = segment) + text blocks split into paragraphs (bullets, line gaps)
Styles inside a paragraph (bold/italic/colour/size) become <gN> tags like in PPTX; the renderer maps them to CSS.
Rotated text is kept as-is and reported.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pymupdf

from sbt.domain.models import DocumentError, DocumentModel, Segment, SegmentKind
from sbt.pipeline.tags import tag_ids

OCR_DPI = 200
pymupdf.no_recommend_layout()      # silence PyMuPDF's suggestion to install its separate layout package
pymupdf.TOOLS.mupdf_display_errors(False)   # damaged files are reported through DocumentModel.notices instead
# List markers kept out of the translation: symbol bullets (space optional), dash bullets (space required,
# so -5 °C is not a bullet), numbers like '2.' or '(3)' not followed by a digit (so 2.1 is not one).
_BULLET = re.compile(r"^\s*([\u2022\u25cf\u25aa\u25e6\u25cb\u25a0\u25a1\u30fb*]\s*|[-\u2013]\s+|\(?\d{1,2}[.)](?!\d)\s*|[a-z][.)]\s+)")
_CJK = re.compile(r"[\u3000-\u30ff\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


# soft hyphen, hyphen, non-breaking hyphen, figure dash → "-"; no-break space → space. (– en dash is kept.)
_SPAN_FIX = str.maketrans({"\u00ad": "-", "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u00a0": " "})


def _norm_spans(spans: list[dict]) -> list[dict]:
    """Text as written: PDFs often encode a visible hyphen as U+00AD (FX<U+00AD>PCG2611 → FX-PCG2611) and use
    non-breaking spaces; both would break identifier protection and matching."""
    out = []
    for sp in spans:
        if not sp["text"]:
            continue
        sp = dict(sp)
        sp["text"] = sp["text"].translate(_SPAN_FIX)
        out.append(sp)
    return out


@dataclass
class _Line:
    text: str
    rect: pymupdf.Rect
    spans: list[dict]


def _style_key(span: dict) -> tuple[bool, bool, int, float]:
    font = span.get("font", "")
    bold = bool(span["flags"] & 16) or "bold" in font.lower()
    italic = bool(span["flags"] & 2) or "italic" in font.lower() or "oblique" in font.lower()
    return bold, italic, int(span.get("color", 0)), round(float(span["size"]) * 2) / 2


def _style_dict(key: tuple[bool, bool, int, float], font: str = "") -> dict[str, object]:
    bold, italic, color, size = key
    serif = any(w in font.lower() for w in ("times", "serif", "mincho", "georgia", "cambria", "song"))
    return {"bold": bold, "italic": italic, "color": f"#{color:06x}", "size": size, "serif": serif}


def _encode(spans: list[dict], joiner_between: list[str]) -> tuple[str, dict[int | None, dict[str, object]]]:
    """Tagged text for a paragraph's spans. joiner_between[i] is inserted after span i (line joins)."""
    weights: Counter[tuple[bool, bool, int, float]] = Counter()
    for sp in spans:
        weights[_style_key(sp)] += len(sp["text"].strip())
    dominant = weights.most_common(1)[0][0] if weights else (False, False, 0, 10.0)
    ids: dict[tuple[bool, bool, int, float], int | None] = {dominant: None}
    fonts: dict[tuple[bool, bool, int, float], str] = {}
    out: list[str] = []
    for sp, joiner in zip(spans, joiner_between, strict=True):
        key = _style_key(sp)
        fonts.setdefault(key, sp.get("font", ""))
        if key not in ids:
            ids[key] = len(ids)
        tid = ids[key]
        text = sp["text"]
        # size-only differences (e.g. 10.5 vs 11 pt) are not worth a tag
        if tid is not None and key[:3] == dominant[:3]:
            tid = None
        out.append(text if tid is None or not text.strip() else f"<g{tid}>{text}</g{tid}>")
        out.append(joiner)
    merged = "".join(out)
    for tid in {i for i in ids.values() if i is not None}:
        merged = merged.replace(f"</g{tid}><g{tid}>", "")
    styles = {tid: _style_dict(k, fonts.get(k, "")) for k, tid in ids.items()}
    return merged.strip(), styles


class PdfParser:
    file_types = frozenset({"pdf"})

    def __init__(self, source_lang: str | None = None, ocr: bool = True) -> None:
        self.source_lang = source_lang
        self.ocr = ocr

    def parse(self, path: Path) -> DocumentModel:
        doc = _open(path)
        model = DocumentModel(str(path), "pdf", doc.page_count)
        if doc.is_repaired:
            model.notices.append("WARNING: the PDF is damaged and was repaired while opening — pages or text may "
                                 "be missing; compare the page count with the original")
        try:
            for pno, page in enumerate(doc, start=1):
                if _is_scanned(page):
                    self._parse_scanned(page, pno, model)
                else:
                    self._parse_text_page(page, pno, model)
        finally:
            doc.close()
        return model

    # --- text pages -----------------------------------------------------------------------------------
    def _parse_text_page(self, page: pymupdf.Page, pno: int, model: DocumentModel) -> None:
        tables = []
        try:
            tables = list(page.find_tables().tables)
        except Exception:          # table detection is best-effort; never fail the page on it
            tables = []
        # a table inside another table is a false detection (e.g. a shaded header cell)
        tables = [t for t in tables if not any(o is not t and pymupdf.Rect(t.bbox) in pymupdf.Rect(o.bbox) + (-1, -1, 1, 1)
                                               for o in tables)]
        table_rects = [pymupdf.Rect(t.bbox) for t in tables]
        for ti, table in enumerate(tables):
            for ci, cell in enumerate(table.cells):
                if cell is None:
                    continue
                rect = pymupdf.Rect(cell)
                self._add_block(page, pno, model, f"p{pno}/t{ti}/c{ci}", SegmentKind.TABLE_CELL,
                                _lines(page, clip=rect), rect_limit=rect)

        data = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
        sizes = [s["size"] for b in data["blocks"] if b["type"] == 0 for ln in b["lines"] for s in ln["spans"]
                 if s["text"].strip()]
        median = float(np.median(sizes)) if sizes else 10.0
        pieces: list[_Line] = []
        for block in data["blocks"]:
            if block["type"] == 1:
                self._check_image(page, pno, block, model)
                continue
            brect = pymupdf.Rect(block["bbox"])
            if any(tr.intersects(brect) and (tr & brect).get_area() > 0.5 * brect.get_area() for tr in table_rects):
                continue
            for ln in block["lines"]:
                if abs(ln["dir"][0] - 1.0) > 0.01:
                    model.untranslatable.append(f"page {pno}: rotated text (kept as-is)")
                    continue
                pieces.extend(_pieces(_norm_spans(ln["spans"])))
        for pi, para in enumerate(_paragraphs(pieces)):
            size = max(float(s["size"]) for ln in para for s in ln.spans)
            text_len = sum(len(ln.text) for ln in para)
            bold = all(_style_key(s)[0] for ln in para for s in ln.spans if s["text"].strip())
            heading = text_len < 100 and (size >= 1.2 * median or (bold and size > median))
            kind = SegmentKind.TITLE if heading else SegmentKind.BODY
            self._add_block(page, pno, model, f"p{pno}/r{pi}", kind, para)

    def _add_block(self, page: pymupdf.Page, pno: int, model: DocumentModel, sid: str, kind: SegmentKind,
                   lines: list[_Line], rect_limit: pymupdf.Rect | None = None) -> None:
        if not lines or not "".join(ln.text for ln in lines).strip():
            return
        prefix = ""
        m = _BULLET.match(lines[0].text)
        if m and len(lines[0].text) > len(m.group(0)):
            prefix = m.group(0)
            lines[0] = _Line(lines[0].text[len(prefix):], lines[0].rect, _drop_chars(lines[0].spans, len(prefix)))
        spans: list[dict] = []
        joiners: list[str] = []
        for i, ln in enumerate(lines):
            for j, sp in enumerate(ln.spans):
                spans.append(sp)
                last_in_line = j == len(ln.spans) - 1
                if not last_in_line or i == len(lines) - 1:
                    joiners.append("")
                    continue
                nxt = lines[i + 1].text
                if ln.text.rstrip().endswith("-") and nxt[:1].islower():
                    sp = dict(sp)
                    sp["text"] = sp["text"].rstrip()[:-1]
                    spans[-1] = sp
                    joiners.append("")
                elif _CJK.search(ln.text[-1:]) or _CJK.search(nxt[:1]):
                    joiners.append("")
                else:
                    joiners.append(" ")
        text, styles = _encode(spans, joiners)
        text = re.sub(r"[ \t]+", " ", text)
        if not text.strip():
            return
        rect = pymupdf.Rect(lines[0].rect)
        for ln in lines[1:]:
            rect |= ln.rect
        align = _alignment(lines, rect)
        model.segments.append(Segment(
            id=sid, kind=kind, container=pno, shape_key=sid.rsplit("/", 1)[0], source=text,
            tag_ids=frozenset(tag_ids(text)),
            geometry={"page": pno - 1, "rect": tuple(rect), "line_rects": [tuple(ln.rect) for ln in lines],
                      "styles": {str(k): v for k, v in styles.items()}, "prefix": prefix, "align": align,
                      "cell": tuple(rect_limit) if rect_limit is not None else None}))

    def _check_image(self, page: pymupdf.Page, pno: int, block: dict, model: DocumentModel) -> None:
        rect = pymupdf.Rect(block["bbox"])
        if not self.ocr or rect.get_area() < 0.03 * page.rect.get_area():
            return
        from sbt.ocr import engine
        img = _render(page, rect)
        if engine.image_has_text(img, self.source_lang or "en"):
            model.untranslatable.append(f"page {pno}: image contains text (not translated)")

    # --- scanned pages --------------------------------------------------------------------------------
    def _parse_scanned(self, page: pymupdf.Page, pno: int, model: DocumentModel) -> None:
        from sbt.ocr import engine
        if not self.ocr:
            model.untranslatable.append(f"page {pno}: scanned page (OCR switched off)")
            return
        lang = self.source_lang or "en"
        image = _render(page, page.rect)
        try:
            lines = engine.read(image, lang)
        except engine.OcrUnavailable as e:
            model.untranslatable.append(f"page {pno}: scanned page, {e}")
            return
        model.notices.append(f"page {pno}: scanned — text read by OCR")
        scale = 72 / OCR_DPI
        paragraphs = engine.group_paragraphs(lines, image)
        heights = [ln.box[3] - ln.box[1] for ln in lines]
        median_h = float(np.median(heights)) if heights else 1.0
        body_size = round(median_h * scale * 0.8 * 2) / 2
        for pi, para in enumerate(paragraphs):
            rects = [pymupdf.Rect(*(v * scale for v in ln.box)) for ln in para]
            rect = pymupdf.Rect(rects[0])
            for r in rects[1:]:
                rect |= r
            joiner = "" if lang in ("ja", "zh") else " "
            text = joiner.join(ln.text for ln in para)
            prefix = ""
            m = _BULLET.match(text)
            if m and len(text) > len(m.group(0)):
                prefix, text = m.group(0), text[len(m.group(0)):]
            height = float(np.median([r.height for r in rects]))
            size = round(height * 0.8 * 2) / 2
            if abs(size - body_size) <= 0.2 * body_size:      # same text size as the body, just a noisier box
                size = body_size
            colour = engine.text_colour(image, [ln.box for ln in para])
            short = len(para) == 1 and len(text) < 60
            numbered = bool(prefix) and prefix.strip()[:1].isdigit()
            heading = short and (float(np.median([ln.box[3] - ln.box[1] for ln in para])) >= 1.25 * median_h
                                 or colour != "#000000" or numbered)
            sid = f"p{pno}/ocr{pi}"
            model.segments.append(Segment(
                id=sid, kind=SegmentKind.TITLE if heading else SegmentKind.IMAGE_TEXT, container=pno,
                shape_key=sid, source=text, ocr_confidence=round(float(np.mean([ln.score for ln in para])), 3),
                geometry={"page": pno - 1, "rect": tuple(rect), "line_rects": [tuple(r) for r in rects],
                          "styles": {"None": {"bold": heading, "italic": False, "color": colour,
                                              "size": size, "serif": False}},
                          "prefix": prefix, "align": "left", "ocr": True}))


def _open(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as e:
        raise DocumentError(f"The PDF could not be opened; the file may be damaged ({type(e).__name__}).") from None
    if doc.needs_pass and not doc.authenticate(""):
        doc.close()
        raise DocumentError("The PDF is password-protected. Open it in a PDF viewer, save an unprotected copy, "
                            "and translate that.")
    if doc.page_count == 0:
        raise DocumentError("The PDF has no pages.")
    return doc


def _drop_chars(spans: list[dict], n: int) -> list[dict]:
    """Remove the first n characters across spans (a bullet can be its own span)."""
    out = []
    for sp in spans:
        if n <= 0:
            out.append(sp)
            continue
        text = sp["text"]
        if len(text) <= n:
            n -= len(text)
            continue
        sp = dict(sp)
        sp["text"] = text[n:]
        n = 0
        out.append(sp)
    return out


def _lines(page: pymupdf.Page, clip: pymupdf.Rect) -> list[_Line]:
    data = page.get_text("dict", clip=clip, flags=pymupdf.TEXTFLAGS_TEXT)
    out = []
    for b in data["blocks"]:
        for ln in b.get("lines", []):
            spans = _norm_spans(ln["spans"])
            if spans:
                out.append(_Line("".join(s["text"] for s in spans), pymupdf.Rect(ln["bbox"]), spans))
    return out


def _pieces(spans: list[dict]) -> list[_Line]:
    """Split one PDF line where spans are far apart: side-by-side labels (diagram boxes, table-like layouts
    without lines) share a baseline but are separate texts."""
    out: list[list[dict]] = []
    for sp in spans:
        if out:
            prev = out[-1][-1]
            gap = sp["bbox"][0] - prev["bbox"][2]
            if gap > 1.5 * max(float(sp["size"]), float(prev["size"])):
                out.append([sp])
                continue
            out[-1].append(sp)
        else:
            out.append([sp])
    lines = []
    for group in out:
        rect = pymupdf.Rect(group[0]["bbox"])
        for sp in group[1:]:
            rect |= pymupdf.Rect(sp["bbox"])
        lines.append(_Line("".join(s["text"] for s in group), rect, group))
    return [ln for ln in lines if ln.text.strip()]


def _line_colour(line: _Line) -> int:
    """Colour used by most characters of a line: a differently coloured line (e.g. a red note under black text)
    is a separate paragraph."""
    weights: Counter[int] = Counter()
    for sp in line.spans:
        weights[int(sp.get("color", 0))] += len(sp["text"].strip())
    return weights.most_common(1)[0][0] if weights else 0


def _paragraphs(lines: list[_Line]) -> list[list[_Line]]:
    """Rebuild paragraphs from line pieces across PDF blocks (exported slides often put every line in its own
    block). A line continues the previous paragraph if it is just below it, overlaps it horizontally, has a
    similar font size and does not start with a bullet."""
    paras: list[list[_Line]] = []
    for ln in lines:
        size = max(float(s["size"]) for s in ln.spans)
        target = None
        for para in reversed(paras[-4:]):
            prev = para[-1]
            psize = max(float(s["size"]) for s in prev.spans)
            gap = ln.rect.y0 - prev.rect.y1
            overlap = min(ln.rect.x1, prev.rect.x1) - max(ln.rect.x0, prev.rect.x0)
            if (-0.3 * prev.rect.height <= gap <= 0.6 * prev.rect.height and overlap > 0
                    and abs(size - psize) <= 0.15 * psize and not _BULLET.match(ln.text)
                    and _line_colour(ln) == _line_colour(prev)):
                target = para
                break
        if target is None:
            paras.append([ln])
        else:
            target.append(ln)
    return paras


def _alignment(lines: list[_Line], rect: pymupdf.Rect) -> str:
    if len(lines) < 2:
        return "left"
    lefts = [ln.rect.x0 - rect.x0 for ln in lines]
    rights = [rect.x1 - ln.rect.x1 for ln in lines]
    if max(lefts) < 2 and max(rights) < 2:
        return "justify"
    if max(lefts) > 4 and all(abs(lft - rgt) < 4 for lft, rgt in zip(lefts, rights, strict=True)):
        return "center"
    if max(rights) < 2 and max(lefts) > 4:
        return "right"
    return "left"


def _is_scanned(page: pymupdf.Page) -> bool:
    chars = len(page.get_text("text").strip())
    if chars >= 20:
        return False
    area = page.rect.get_area() or 1
    covered = sum(pymupdf.Rect(img["bbox"]).get_area() for img in page.get_image_info())
    return covered / area > 0.5


def _render(page: pymupdf.Page, rect: pymupdf.Rect) -> np.ndarray:
    pix = page.get_pixmap(dpi=OCR_DPI, clip=rect, colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
