"""Fonts in a translated PowerPoint file: is the font installed, and does it contain every character?

PowerPoint picks the font per character class: Latin text uses <a:latin>, Japanese/Chinese/Korean <a:ea>,
Thai/Burmese <a:cs>; "+mn-ea" etc. point to the theme. A missing font or glyph is replaced by Windows
font fallback, so the slide still shows text but looks different (info); a character no installed font
can draw shows as a box (warning).
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from lxml import etree

from sbt.domain.models import Severity
from sbt.quality.findings import Finding
from sbt.winfonts import WINDOWS_FONTS, A, family_key, installed, theme_fonts

_FALLBACK = ["segoe ui", "segoe ui symbol", "segoe ui emoji", "segoe ui historic", "meiryo", "yu gothic",
             "ms gothic", "malgun gothic", "microsoft yahei", "simsun", "leelawadee ui", "myanmar text",
             "nirmala ui", "arial", "cambria math", "ebrima", "gadugi"]
_STYLE = re.compile(r"\s+(regular|bold|italic|light|semilight|semibold|black|oblique|medium|condensed|book)\b.*$")
_CHILD = {"lt": "latin", "ea": "ea", "cs": "cs"}
_CS = re.compile(r"[\u0e00-\u0e7f\u1000-\u109f\u0590-\u06ff\u0900-\u097f]")


@lru_cache(maxsize=64)
def _font(path: Path):  # type: ignore[no-untyped-def]
    import pymupdf
    try:
        return pymupdf.Font(fontfile=str(path))
    except Exception:  # noqa: BLE001 - unreadable font file: treat as not installed
        return None


def has_glyph(family: str, ch: str) -> bool | None:
    """True/False, or None when the font is not installed."""
    path = installed().get(family_key(family))
    font = _font(path) if path else None
    return None if font is None else bool(font.has_glyph(ord(ch)))


def _drawable_by_any(ch: str) -> bool:
    return any(has_glyph(f, ch) for f in _FALLBACK)


def _klass(ch: str, lang: str) -> str:
    if _CS.match(ch):
        return "cs"
    width = unicodedata.east_asian_width(ch)
    if width in ("W", "F") or (width == "A" and lang in ("ja", "zh", "ko") and ord(ch) > 0x2000):
        return "ea"
    return "lt"


def check_pptx(output: Path, segment_ids: set[str], lang: str) -> list[Finding]:
    from pptx import Presentation
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT

    from sbt.parsers.pptx_walk import ParagraphRef, walk
    if not installed():
        return []
    prs = Presentation(str(output))
    themes: dict[int, dict[str, str]] = {}

    def theme_for(slide_no: int) -> dict[str, str]:
        if slide_no not in themes:
            try:
                master = prs.slides[slide_no - 1].slide_layout.slide_master
                themes[slide_no] = theme_fonts(etree.fromstring(master.part.part_related_by(RT.THEME).blob), lang)
            except (IndexError, KeyError, etree.XMLSyntaxError):
                themes[slide_no] = {}
        return themes[slide_no]

    missing_font: dict[str, list[ParagraphRef]] = defaultdict(list)
    substituted: dict[str, tuple[set[str], list[ParagraphRef]]] = defaultdict(lambda: (set(), []))
    boxes: dict[str, list[ParagraphRef]] = defaultdict(list)
    for item in walk(prs):
        if not isinstance(item, ParagraphRef) or item.segment_id not in segment_ids:
            continue
        theme = theme_for(item.slide_no)
        level = "mj" if item.kind.value == "title" else "mn"
        for r in item.element.iter(f"{A}r"):
            text = "".join(t.text or "" for t in r.iter(f"{A}t"))
            rpr = r.find(f"{A}rPr")
            for ch in dict.fromkeys(c for c in text if not c.isspace()):
                klass = _klass(ch, lang)
                el = rpr.find(f"{A}{_CHILD[klass]}") if rpr is not None else None
                face = el.get("typeface", "") if el is not None else f"+{level}-{klass}"
                face = theme.get(face, "") if face.startswith("+") else face
                if not face:                  # template leaves it to Windows' default font for the language
                    continue
                ok = has_glyph(face, ch)
                if ok is None:
                    missing_font[face].append(item)
                elif not ok:
                    if _drawable_by_any(ch):
                        substituted[face][0].add(ch)
                        substituted[face][1].append(item)
                    else:
                        boxes[ch].append(item)
    found = []
    for face, refs in missing_font.items():
        found.append(Finding("layout", "font_not_installed", Severity.INFO,
                             f"a font used in {len(_ids(refs))} paragraph(s) is not installed on this PC "
                             "(PowerPoint shows a substitute)", _ids(refs), _slides(refs), detail={"font": face}))
    for face, (chars, refs) in substituted.items():
        found.append(Finding("layout", "substitute_font", Severity.INFO,
                             f"{len(chars)} character(s) not in the chosen font (PowerPoint shows a substitute)",
                             _ids(refs), _slides(refs), detail={"font": face, "characters": "".join(sorted(chars))}))
    if boxes:
        refs = [r for rs in boxes.values() for r in rs]
        found.append(Finding("layout", "missing_glyphs", Severity.WARNING,
                             f"{len(boxes)} character(s) no installed font can display (shown as boxes)",
                             _ids(refs), _slides(refs), detail={"characters": "".join(sorted(boxes))}))
    return found


def pdf_font_names(lang: str) -> tuple[str, ...]:
    """Normalised names of the fonts the PDF writer uses for this language (to recognise substitutes)."""
    from sbt.renderers import fonts as pdf_fonts
    fs = pdf_fonts.for_language(lang)
    names = []
    for file in {fs.sans, fs.sans_bold, fs.serif, fs.serif_bold}:
        f = _font(WINDOWS_FONTS / file)
        if f is not None:
            names.append(re.sub(r"[^a-z0-9]", "", _STYLE.sub("", f.name.lower())))
    return tuple(names)


def _ids(refs: list) -> list[str]:  # type: ignore[type-arg]
    return list(dict.fromkeys(r.segment_id for r in refs))


def _slides(refs: list) -> list[int]:  # type: ignore[type-arg]
    return sorted({r.slide_no for r in refs})
