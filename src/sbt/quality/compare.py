"""Pair an original document with a translation made elsewhere, so the quality checks can run on it.

PowerPoint: paragraphs are matched by position in the file (slide, shape, paragraph), which a translator
working in PowerPoint keeps. PDF: text blocks are matched by page and position (overlapping boxes); a PDF that
was re-laid out matches poorly, which shows up as "not translated" findings.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sbt import formats, languages
from sbt.domain.models import DocumentError, DocumentModel, Issue, Segment, Severity
from sbt.pipeline.tags import strip_tags


def _overlap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Intersection area as a share of the smaller box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1.0
    return w * h / smaller


def load_pair(original: Path, translated: Path, src: str, ocr: bool = True) -> DocumentModel:
    if original.suffix.lower() != translated.suffix.lower():
        raise DocumentError("The original and the translation must be the same file type.")
    formats.check_supported(original)
    formats.check_supported(translated)
    doc = formats.parser_for(original, src, ocr).parse(original)
    other = formats.parser_for(translated, None, ocr).parse(translated)
    if doc.container_count != other.container_count:
        unit = "pages" if original.suffix.lower() == ".pdf" else "slides"
        raise DocumentError(f"The files have a different number of {unit} ({doc.container_count} and "
                            f"{other.container_count}). Choose the translation of this document.")
    if original.suffix.lower() == ".pptx":
        by_id = {s.id: s for s in other.segments}
        for s in doc.segments:
            t = by_id.get(s.id)
            s.translation = strip_tags(t.source) if t is not None else None
    else:
        _match_pdf(doc.segments, other.segments)
    doc.notices = list(doc.notices) + [n for n in other.notices if n not in doc.notices]
    return doc


def _match_pdf(segments: list[Segment], others: list[Segment]) -> None:
    by_page: dict[int, list[Segment]] = defaultdict(list)
    for o in others:
        by_page[int(o.geometry.get("page", -1))].append(o)  # type: ignore[call-overload]
    used: set[str] = set()
    for s in segments:
        rect = s.geometry.get("rect")
        if rect is None:
            continue
        hits = [o for o in by_page[int(s.geometry["page"])]  # type: ignore[call-overload]
                if o.id not in used and _overlap(tuple(rect), tuple(o.geometry["rect"])) >= 0.5]  # type: ignore[arg-type]
        if hits:
            hits.sort(key=lambda o: (o.geometry["rect"][1], o.geometry["rect"][0]))  # type: ignore[index]
            used.update(o.id for o in hits)
            s.translation = "\n".join(strip_tags(o.source) for o in hits)


def layout_issues(original: Path, translated: Path, src: str, tgt: str) -> list[Issue]:
    """PowerPoint: text boxes whose translated text likely needs more room than the box (and than the original
    text needed, so boxes that already overflowed are not blamed on the translation)."""
    if translated.suffix.lower() != ".pptx":
        return []
    from sbt.parsers.pptx_parser import open_presentation
    from sbt.parsers.pptx_walk import A, ParagraphRef, walk
    from sbt.renderers.text_fit import estimate_height

    def heights(path: Path, lang: str) -> dict[str, tuple[float, float, int]]:
        out = {}
        for item in walk(open_presentation(path)):
            if isinstance(item, ParagraphRef) and item.shape is not None and item.shape_key not in out:
                body = item.shape.text_frame._txBody.find(f"{A}bodyPr")
                if body is not None and body.find(f"{A}spAutoFit") is not None:
                    continue
                needed, box = estimate_height(item.shape, languages.get(lang))
                out[item.shape_key] = (needed, box, item.slide_no)
        return out

    before = heights(original, src)
    issues = []
    for key, (needed, box, slide) in heights(translated, tgt).items():
        limit = max(box, before.get(key, (0.0, 0.0, 0))[0])
        if needed > limit * 1.05:
            issues.append(Issue("overflow", Severity.WARNING, key, f"slide {slide}: text likely exceeds its box"))
    return issues
