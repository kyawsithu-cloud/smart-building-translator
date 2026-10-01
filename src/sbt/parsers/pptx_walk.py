"""Deterministic traversal of a presentation's text, shared by the PPTX parser and renderer.

The parser and renderer both open the ORIGINAL file and walk it in the same order, so a segment id such as
"s3/12/p0" always identifies the same paragraph. No state needs to be kept between the two.
"""
from __future__ import annotations

import copy
from collections.abc import Iterator
from dataclasses import dataclass

from lxml import etree
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.presentation import Presentation as PresentationT
from pptx.text.text import TextFrame

from sbt.domain.models import SegmentKind

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
# rPr attributes that do not affect appearance; ignored when grouping runs into formatting classes.
_VOLATILE_ATTRS = ("lang", "altLang", "dirty", "err", "noProof", "smtClean", "smtId", "bmk")


@dataclass
class ParagraphRef:
    segment_id: str
    kind: SegmentKind
    slide_no: int
    shape_key: str
    element: etree._Element           # a:p
    text_frame: TextFrame
    shape: object | None              # owning shape (None for table cells / notes: sized differently)


@dataclass
class EncodedParagraph:
    text: str                                       # tagged text
    class_rpr: dict[int | None, etree._Element | None]   # tag id -> rPr template (None key = dominant)
    has_field: bool


def _class_key(rpr: etree._Element | None) -> str:
    if rpr is None:
        return ""
    clean = copy.deepcopy(rpr)
    for attr in _VOLATILE_ATTRS:
        clean.attrib.pop(attr, None)
    return etree.tostring(clean, method="c14n").decode()


def encode_paragraph(p: etree._Element) -> EncodedParagraph:
    pieces: list[tuple[str, str]] = []           # (class key, text)
    rprs: dict[str, etree._Element | None] = {}
    has_field = False
    for child in p:
        tag = etree.QName(child).localname
        if tag in ("r", "fld"):
            has_field |= tag == "fld"
            rpr = child.find(f"{A}rPr")
            key = _class_key(rpr)
            rprs.setdefault(key, rpr)
            t = child.find(f"{A}t")
            pieces.append((key, (t.text or "") if t is not None else ""))
        elif tag == "br":
            rpr = child.find(f"{A}rPr")
            key = pieces[-1][0] if pieces else _class_key(rpr)
            rprs.setdefault(key, rpr)
            pieces.append((key, "\n"))

    # Dominant class = most characters; it stays untagged to keep prompts simple.
    totals: dict[str, int] = {}
    for key, text in pieces:
        totals[key] = totals.get(key, 0) + len(text.strip())
    dominant = max(totals, key=lambda k: totals[k]) if totals else ""
    ids: dict[str, int | None] = {dominant: None}
    for key, _ in pieces:
        if key not in ids:
            ids[key] = len(ids)          # 1, 2, … in order of first appearance

    out: list[str] = []
    for key, text in pieces:
        tid = ids[key]
        if tid is None or not text.strip():   # whitespace-only spans don't need their own tag
            out.append(text)
        else:
            out.append(f"<g{tid}>{text}</g{tid}>")
    merged = "".join(out)
    # merge adjacent identical tags produced by consecutive runs of the same class
    for tid in set(i for i in ids.values() if i is not None):
        merged = merged.replace(f"</g{tid}><g{tid}>", "")
    # .get: a paragraph can have no runs at all (empty line), so the dominant class may have no rPr
    return EncodedParagraph(merged, {tid: rprs.get(key) for key, tid in ids.items()}, has_field)


def _iter_shape(shape, slide_no: int, prefix: str) -> Iterator[ParagraphRef | str]:
    key = f"{prefix}/{shape.shape_id}"
    st = shape.shape_type
    if st == MSO_SHAPE_TYPE.GROUP:
        for sub in shape.shapes:
            yield from _iter_shape(sub, slide_no, key)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        for r, row in enumerate(shape.table.rows):
            for c, cell in enumerate(row.cells):
                if cell.is_spanned:
                    continue
                ck = f"{key}/t{r}.{c}"
                for i, p in enumerate(cell.text_frame.paragraphs):
                    yield ParagraphRef(f"{ck}/p{i}", SegmentKind.TABLE_CELL, slide_no, ck, p._p,
                                       cell.text_frame, None)
        return
    if getattr(shape, "has_chart", False) and shape.has_chart:
        yield f"slide {slide_no}: chart (chart text not translated in this version)"
        return
    if st == MSO_SHAPE_TYPE.PICTURE:
        yield f"slide {slide_no}: picture (text inside images is not translated)"
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        kind = SegmentKind.BODY
        if shape.is_placeholder and shape.placeholder_format.type in (
                PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE):
            kind = SegmentKind.TITLE
        for i, p in enumerate(shape.text_frame.paragraphs):
            yield ParagraphRef(f"{key}/p{i}", kind, slide_no, key, p._p, shape.text_frame, shape)
    elif st not in (MSO_SHAPE_TYPE.LINE, None) and shape.element.tag.endswith("graphicFrame"):
        yield f"slide {slide_no}: embedded object (not translated)"


def walk(prs: PresentationT) -> Iterator[ParagraphRef | str]:
    """Yields ParagraphRef for every paragraph, or a string describing content that cannot be translated."""
    for n, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            yield from _iter_shape(shape, n, f"s{n}")
        if slide.has_notes_slide:
            tf = slide.notes_slide.notes_text_frame
            if tf is not None:
                for i, p in enumerate(tf.paragraphs):
                    yield ParagraphRef(f"s{n}/notes/p{i}", SegmentKind.NOTE, n, f"s{n}/notes", p._p, tf, None)
