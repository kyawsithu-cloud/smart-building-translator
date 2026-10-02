"""Writes translations into a copy of the source presentation."""
from __future__ import annotations

import copy
from pathlib import Path

from lxml import etree

from sbt import languages
from sbt.domain.models import DocumentModel, Issue, Severity
from sbt.parsers.pptx_parser import open_presentation
from sbt.parsers.pptx_walk import (A, ParagraphRef, SmartArtRef, TextNodeRef, encode_paragraph, flush_parts,
                                   walk)
from sbt.pipeline.tags import split_spans, strip_tags
from sbt.renderers.text_fit import estimate_height, fit_text_frame


# Used only when the deck's theme defines no font for the target script (e.g. an English template).
DEFAULT_EA_FONT = {"ja": "Meiryo UI", "zh": "Microsoft YaHei UI", "ko": "Malgun Gothic"}
_RPR_CHILD_ORDER = ["ln", "noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill", "effectLst",
                    "effectDag", "highlight", "uLnTx", "uLn", "uFillTx", "uFill", "latin", "ea", "cs", "sym",
                    "hlinkClick", "hlinkMouseOver", "rtl", "extLst"]


def _set_ea_font(rpr: etree._Element, typeface: str) -> None:
    if rpr.find(f"{A}ea") is not None:
        return
    ea = etree.Element(f"{A}ea", typeface=typeface)
    after = _RPR_CHILD_ORDER.index("ea")
    for child in rpr:
        name = etree.QName(child).localname
        if name in _RPR_CHILD_ORDER and _RPR_CHILD_ORDER.index(name) > after:
            child.addprevious(ea)
            return
    rpr.append(ea)


def theme_ea_font(prs) -> str:
    """The theme's East Asian body font ('' when the template defines none)."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    try:
        theme = prs.slide_master.part.part_related_by(RT.THEME)
        root = etree.fromstring(theme.blob)
        ea = root.find(f".//{A}minorFont/{A}ea")
        return ea.get("typeface", "") if ea is not None else ""
    except (KeyError, etree.XMLSyntaxError):
        return ""


def _make_run(rpr: etree._Element | None, text: str, lang: str, ea_font: str = "") -> etree._Element:
    r = etree.Element(f"{A}r")
    new_rpr = copy.deepcopy(rpr) if rpr is not None else etree.Element(f"{A}rPr")
    new_rpr.set("lang", lang)
    new_rpr.attrib.pop("altLang", None)
    if ea_font:
        _set_ea_font(new_rpr, ea_font)
    r.append(new_rpr)
    t = etree.SubElement(r, f"{A}t")
    t.text = text
    return r


def _make_br(rpr: etree._Element | None, lang: str) -> etree._Element:
    br = etree.Element(f"{A}br")
    new_rpr = copy.deepcopy(rpr) if rpr is not None else etree.Element(f"{A}rPr")
    new_rpr.set("lang", lang)
    br.append(new_rpr)
    return br


def replace_paragraph_text(ref: ParagraphRef, translation: str, lang: str, ea_font: str = "") -> None:
    p = ref.element
    enc = encode_paragraph(p)
    for child in list(p):
        if etree.QName(child).localname in ("r", "br", "fld"):
            p.remove(child)
    end = p.find(f"{A}endParaRPr")
    new_nodes: list[etree._Element] = []
    for tid, text in split_spans(translation):
        rpr = enc.class_rpr.get(tid, enc.class_rpr.get(None))
        for i, line in enumerate(text.split("\n")):
            if i:
                new_nodes.append(_make_br(rpr, lang))
            if line:
                new_nodes.append(_make_run(rpr, line, lang, ea_font))
    for node in new_nodes:
        if end is not None:
            end.addprevious(node)
        else:
            p.append(node)


class PptxRenderer:
    file_types = frozenset({"pptx"})

    def __init__(self, source_lang: str, target_lang: str, min_font_scale: float = 0.8) -> None:
        self.source_lang = languages.get(source_lang)
        self.lang = languages.get(target_lang)
        self.min_font_scale = min_font_scale

    def render(self, model: DocumentModel, output_path: Path) -> list[Issue]:
        if Path(output_path).resolve() == Path(model.source_path).resolve():
            raise ValueError("Refusing to overwrite the original document")
        prs = open_presentation(Path(model.source_path))
        by_id = {s.id: s for s in model.segments}
        smartarts: list[SmartArtRef] = []
        ea_font = "" if theme_ea_font(prs) else DEFAULT_EA_FONT.get(self.lang.code, "")
        frames: dict[str, ParagraphRef] = {}
        baseline: dict[str, float] = {}    # source text height: never "fix" a box that already overflowed
        for item in walk(prs):
            if isinstance(item, SmartArtRef):
                smartarts.append(item)
                continue
            if not isinstance(item, (ParagraphRef, TextNodeRef)):
                continue
            seg = by_id.get(item.segment_id)
            if seg is None or seg.translation is None:
                continue
            if isinstance(item, TextNodeRef):
                item.element.text = strip_tags(seg.translation)
                continue
            if item.shape_key not in frames and item.shape is not None:
                baseline[item.shape_key] = estimate_height(item.shape, self.source_lang)[0]
            replace_paragraph_text(item, seg.translation, self.lang.ooxml_lang, ea_font)
            frames.setdefault(item.shape_key, item)

        for sa in smartarts:
            self._sync_smartart_drawing(sa, model)
        flush_parts(prs)

        issues: list[Issue] = []
        for key, ref in frames.items():
            if ref.shape is None:          # table cells grow; notes have no box
                continue
            result = fit_text_frame(ref.shape, self.lang, self.min_font_scale, baseline.get(key))
            if result.overflow:
                issues.append(Issue("overflow", Severity.WARNING, key,
                                    f"slide {ref.slide_no}: text likely exceeds its box even at "
                                    f"{int(result.scale * 100)}% font size"))
            elif result.scale < 1.0:
                issues.append(Issue("font_reduced", Severity.INFO, key,
                                    f"slide {ref.slide_no}: font reduced to {int(result.scale * 100)}% to fit"))
        prs.save(str(output_path))
        return issues

    def _sync_smartart_drawing(self, sa: SmartArtRef, model: DocumentModel) -> None:
        """PowerPoint shows SmartArt from a cached drawing; give its paragraphs the same translations."""
        if sa.drawing is None:
            return
        by_text = {s.plain_source.strip(): s.translation for s in model.segments
                   if s.shape_key == sa.shape_key and s.translation}
        for p in sa.drawing.iter(f"{A}p"):
            plain = strip_tags(encode_paragraph(p).text).strip()
            translation = by_text.get(plain)
            if translation:
                ref = ParagraphRef("", model.segments[0].kind, sa.slide_no, sa.shape_key, p, None, None)
                replace_paragraph_text(ref, translation, self.lang.ooxml_lang)
