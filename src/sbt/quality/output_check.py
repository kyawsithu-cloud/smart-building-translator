"""Reads the written file back and compares it with what should be in it.

Independent of the renderer's own bookkeeping: if a paragraph, a chart label or a SmartArt drawing was not
written, or the original text is still visible on a PDF page, this finds it. Never silently ship a partially
translated document.

  not_written      the translation is not in the output file
  original_left    (PDF) the original text is still extractable on the page
  substitute_font  (PDF) characters drawn with a fallback font because the chosen font lacks them
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from lxml import etree
from rapidfuzz import fuzz

from sbt.domain.models import DocumentModel, Severity
from sbt.pipeline.tags import strip_tags
from sbt.quality.findings import Finding

_SQUASH = re.compile(r"[\s\xad\u200b]+")          # whitespace, soft hyphen, zero-width space
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_DRAWING = "application/vnd.ms-office.drawingml.diagramDrawing+xml"


def squash(text: str) -> str:
    """Comparable form: no whitespace; NFKC because PDF text extraction can return look-alike code points
    (Kangxi radical ⽅ for 方, ℃ for °C) for the very glyphs that were written."""
    return _SQUASH.sub("", unicodedata.normalize("NFKC", text))


def _written(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    return len(expected) >= 8 and fuzz.ratio(expected, actual) >= 92


def check(doc: DocumentModel, output: Path, original: Path | None = None, font_names: tuple[str, ...] = ()
          ) -> tuple[list[Finding], int]:
    """(findings, paragraphs verified)."""
    if output.suffix.lower() == ".pptx":
        return _pptx(doc, output)
    if output.suffix.lower() == ".pdf":
        return _pdf(doc, output, original, font_names)
    return [], 0


def _pptx(doc: DocumentModel, output: Path) -> tuple[list[Finding], int]:
    from pptx import Presentation

    from sbt.parsers.pptx_parser import PptxParser
    written = {s.id: squash(s.plain_source) for s in PptxParser(ocr_images=False).parse(output).segments}
    found, verified = [], 0
    pending = []
    for s in doc.segments:
        if s.translation is None:
            continue
        expected = squash(strip_tags(s.translation))
        actual = written.get(s.id)
        verified += 1
        if actual is None or not _written(expected, actual):
            found.append(Finding("completeness", "not_written", Severity.ERROR,
                                 f"slide {s.container}: translation missing in the written file",
                                 [s.id], [s.container]))
        elif squash(s.plain_source) != expected:
            pending.append(s)
    # SmartArt: PowerPoint shows the cached drawing part, not the data part the parser reads.
    drawn: set[str] = set()
    prs = Presentation(str(output))
    for part in prs.part.package.iter_parts():
        if part.content_type == _DRAWING:
            root = etree.fromstring(part.blob)
            for p in root.iter(f"{_A}p"):
                text = squash("".join(t.text or "" for t in p.iter(f"{_A}t")))
                if text:
                    drawn.add(text)
    for s in pending:
        src = squash(s.plain_source)
        if "/smartart/" in s.id and len(src) >= 3 and src in drawn:
            found.append(Finding("completeness", "not_written", Severity.ERROR,
                                 f"slide {s.container}: SmartArt still shows the original text",
                                 [s.id], [s.container]))
    return found, verified


def _pdf(doc: DocumentModel, output: Path, original: Path | None, font_names: tuple[str, ...]
         ) -> tuple[list[Finding], int]:
    import pymupdf
    found: list[Finding] = []
    verified = 0
    by_page: dict[int, list] = defaultdict(list)
    for s in doc.segments:
        if s.translation is not None and "page" in s.geometry:
            by_page[int(s.geometry["page"])].append(s)  # type: ignore[call-overload]
    with pymupdf.open(output) as out:
        orig_fonts: dict[int, set[str]] = {}
        if original is not None and original.exists():
            with pymupdf.open(original) as src_pdf:
                orig_fonts = {i: {f[3] for f in p.get_fonts()} for i, p in enumerate(src_pdf)}
        for pno, segs in by_page.items():
            if pno >= out.page_count:
                continue
            page = out[pno]
            text = squash(page.get_text("text"))
            for s in segs:
                expected = squash(strip_tags(s.translation or ""))
                if not expected or expected == squash(s.plain_source):   # unchanged (kept): nothing written
                    continue
                verified += 1
                # Look where the paragraph was: the writer may grow its box to the right and downwards. A short
                # word ("Protocol" → プロトコル) can appear elsewhere on the page, so it must be found here.
                x0, y0, _, y1 = s.geometry["rect"]  # type: ignore[misc]
                area = pymupdf.Rect(x0 - 3, y0 - 3, page.rect.x1, min(page.rect.y1, y1 + (y1 - y0) + 24))
                local = squash(page.get_text("text", clip=area))
                here = expected in local or (len(expected) >= 8 and fuzz.partial_ratio(expected, local) >= 90)
                if not here and (len(expected) < 20 or fuzz.partial_ratio(expected, text) < 90):
                    found.append(Finding("completeness", "not_written", Severity.ERROR,
                                         f"page {s.container}: translation missing in the written file",
                                         [s.id], [s.container]))
                src = squash(s.plain_source)
                if s.ocr_confidence is None and len(src) >= 4 and src != expected and src not in expected \
                        and src in local:
                    found.append(Finding("completeness", "original_left", Severity.ERROR,
                                         f"page {s.container}: original text still visible",
                                         [s.id], [s.container]))
            extra = {f[3] for f in page.get_fonts()} - orig_fonts.get(pno, set())
            subst = sorted(f for f in extra if not any(n in re.sub(r"[^a-z0-9]", "", f.lower()) for n in font_names))
            if subst:
                found.append(Finding("layout", "substitute_font", Severity.INFO,
                                     f"page {s.container}: some characters use a substitute font",
                                     [], [s.container], detail={"fonts": subst}))
    return found, verified
