"""Approximate text layout for overflow detection and gentle font reduction.

python-pptx has no layout engine, so we estimate: resolve each paragraph's effective font size through the
inheritance chain (run → shape list style → layout/master placeholder → master text styles), measure with a
real Windows font via Pillow, wrap greedily, and compare the resulting height to the box. It is an estimate;
the report says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from lxml import etree
from PIL import ImageFont

from sbt.languages import Language
from sbt.parsers.pptx_walk import A

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
EMU_PER_PT = 12700
DEFAULT_SZ = 18.0
LINE_FACTOR = 1.2
FONTS = Path(r"C:\Windows\Fonts")
_FONT_FILES = {
    "ja": ["meiryo.ttc", "YuGothM.ttc", "msgothic.ttc"],
    "zh": ["msyh.ttc", "simsun.ttc"],
    "ko": ["malgun.ttf"],
    "th": ["LeelawUI.ttf", "tahoma.ttf"],
    "my": ["mmrtext.ttf"],
    "*": ["calibri.ttf", "arial.ttf"],
}
_TOKEN = re.compile(r"[A-Za-z0-9\u00C0-\u024F\-./:@_%°±+#()]+\s*|\s+|.", re.S)


@dataclass
class FitResult:
    scale: float
    overflow: bool


@lru_cache(maxsize=8)
def _font(lang_code: str) -> ImageFont.FreeTypeFont | None:
    for name in _FONT_FILES.get(lang_code, []) + _FONT_FILES["*"]:
        path = FONTS / name
        if path.exists():
            return ImageFont.truetype(str(path), 100)
    return None


def _text_width_pt(text: str, size_pt: float, lang: Language) -> float:
    # PowerPoint renders Latin characters with the Latin theme font even in Japanese text.
    native = lang.script is not None and lang.code != "en" and lang.script.search(text) and not text.isascii()
    font = _font(lang.code if native else "*")
    if font is None:
        return len(text) * size_pt * (1.0 if lang.east_asian else 0.5)
    return font.getlength(text) * size_pt / 100


def _lvl_sz(lst_style: etree._Element | None, lvl: int) -> float | None:
    if lst_style is None:
        return None
    d = lst_style.find(f"{A}lvl{lvl + 1}pPr/{A}defRPr")
    if d is not None and d.get("sz"):
        return int(d.get("sz")) / 100
    return None


def _inherited_sz(shape, lvl: int) -> float:
    """Walk placeholder inheritance to find the default size for paragraphs at this level."""
    node = shape
    for _ in range(3):   # slide → layout → master
        body = node.element.find(f".//{P}txBody")
        sz = _lvl_sz(body.find(f"{A}lstStyle") if body is not None else None, lvl)
        if sz:
            return sz
        node = getattr(node, "_base_placeholder", None) if node.is_placeholder else None
        if node is None:
            break
    try:
        master = shape.part.slide.slide_layout.slide_master.element
    except AttributeError:
        return DEFAULT_SZ
    style = "otherStyle"
    if shape.is_placeholder:
        style = "titleStyle" if "title" in str(shape.placeholder_format.type).lower() else "bodyStyle"
    sz = _lvl_sz(master.find(f"{P}txStyles/{P}{style}"), lvl)
    return sz or DEFAULT_SZ


def _paragraph_sizes(shape) -> list[tuple[str, float, list[etree._Element]]]:
    """(text, effective size pt, rPr elements to scale) for each paragraph."""
    out = []
    for p in shape.text_frame.paragraphs:
        rprs = [r for r in p._p.iter(f"{A}rPr", f"{A}endParaRPr")]
        explicit = [int(r.get("sz")) / 100 for r in rprs if r.get("sz")]
        size = max(explicit) if explicit else _inherited_sz(shape, p.level)
        text = "".join(t.text or "" for t in p._p.iter(f"{A}t"))
        out.append((text, size, rprs))
    return out


def _box(shape) -> tuple[float, float, bool]:
    body = shape.text_frame._txBody.find(f"{A}bodyPr")
    get = lambda k, d: int(body.get(k)) if body is not None and body.get(k) else d  # noqa: E731
    w = (shape.width - get("lIns", 91440) - get("rIns", 91440)) / EMU_PER_PT
    h = (shape.height - get("tIns", 45720) - get("bIns", 45720)) / EMU_PER_PT
    wrap = body is None or body.get("wrap") != "none"
    return w, h, wrap


def _lines(text: str, size: float, width: float, lang: Language, wrap: bool) -> tuple[int, float]:
    """Returns (line count, widest line width)."""
    count, widest = 0, 0.0
    for hard_line in text.split("\n") or [""]:
        count += 1
        line_w = 0.0
        for tok in _TOKEN.findall(hard_line):
            w = _text_width_pt(tok, size, lang)
            if wrap and line_w + w > width and line_w > 0:
                count += 1
                widest = max(widest, line_w)
                line_w = _text_width_pt(tok.lstrip(), size, lang)
            else:
                line_w += w
        widest = max(widest, line_w)
    return count, widest


def estimate_height(shape, lang: Language, scale: float = 1.0) -> tuple[float, float]:
    """(needed height pt, box height pt)."""
    width, height, wrap = _box(shape)
    total = 0.0
    for text, size, _ in _paragraph_sizes(shape):
        n, widest = _lines(text, size * scale, width, lang, wrap)
        total += n * size * scale * LINE_FACTOR
        if not wrap and widest > width:
            total = max(total, height * widest / width)   # treat horizontal overflow as overflow
    return total, height


def fit_text_frame(shape, lang: Language, min_scale: float, allowed_height: float | None = None) -> FitResult:
    body = shape.text_frame._txBody.find(f"{A}bodyPr")
    if body is not None and body.find(f"{A}spAutoFit") is not None:
        return FitResult(1.0, False)      # shape grows with its text
    needed, box_h = estimate_height(shape, lang)
    limit = max(box_h, allowed_height or 0.0)
    if needed <= limit:
        return FitResult(1.0, False)
    scale = 1.0
    while scale - 0.05 >= min_scale - 1e-9:
        scale = round(scale - 0.05, 2)
        if estimate_height(shape, lang, scale)[0] <= limit:
            break
    for p in shape.text_frame.paragraphs:
        inherited = _inherited_sz(shape, p.level)
        for rpr in p._p.iter(f"{A}rPr", f"{A}endParaRPr"):
            size = int(rpr.get("sz")) / 100 if rpr.get("sz") else inherited
            rpr.set("sz", str(int(round(size * scale * 100))))
    return FitResult(scale, estimate_height(shape, lang, 1.0)[0] > limit)
