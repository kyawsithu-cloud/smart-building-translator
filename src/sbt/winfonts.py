"""Windows fonts: which fonts are installed (font registry), the file and face of a family, and a
presentation theme's fonts per script. Used to measure text like PowerPoint does and to check glyphs."""
from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from lxml import etree

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
SCRIPT_TAG = {"ja": "Jpan", "zh": "Hans", "ko": "Hang", "th": "Thai", "my": "Mymr"}
# Localised family names used in Japanese/Chinese/Korean templates → the registry's English names.
_ALIASES = {"メイリオ": "meiryo", "游ゴシック": "yu gothic", "游明朝": "yu mincho", "ms pゴシック": "ms pgothic",
            "ms ゴシック": "ms gothic", "ms 明朝": "ms mincho", "ms p明朝": "ms pmincho", "微软雅黑": "microsoft yahei",
            "宋体": "simsun", "黑体": "simhei", "等线": "dengxian", "맑은 고딕": "malgun gothic", "굴림": "gulim",
            "바탕": "batang", "新細明體": "pmingliu", "微軟正黑體": "microsoft jhenghei"}
_STYLE = re.compile(r"\s+(regular|bold|italic|light|semilight|semibold|black|oblique|medium|condensed|book)\b.*$")


def family_key(name: str) -> str:
    k = unicodedata.normalize("NFKC", name).strip().lower()
    return _ALIASES.get(k, k)


@lru_cache(maxsize=1)
def installed() -> dict[str, Path]:
    """Family name (lowercase) → font file, from the Windows font registry (machine and user)."""
    out: dict[str, Path] = {}
    try:
        import winreg
    except ImportError:                       # not Windows
        return out
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
            except OSError:
                break
            i += 1
            path = Path(value) if os.path.isabs(str(value)) else WINDOWS_FONTS / str(value)
            label = re.sub(r"\s*\([^)]*\)\s*$", "", name)
            for family in label.split("&"):
                fam = family.strip().lower()
                out.setdefault(fam, path)
                out.setdefault(_STYLE.sub("", fam), path)
    return out


@lru_cache(maxsize=128)
def face(family: str) -> tuple[Path, int] | None:
    """Font file and face index (a .ttc holds several families, e.g. Meiryo and Meiryo UI)."""
    path = installed().get(family_key(family))
    if path is None or not path.exists():
        return None
    if path.suffix.lower() != ".ttc":
        return path, 0
    from PIL import ImageFont
    wanted = family_key(family)
    for index in range(16):
        try:
            name = ImageFont.truetype(str(path), 10, index=index).getname()[0]
        except OSError:
            break
        if name.lower() == wanted or _STYLE.sub("", name.lower()) == wanted:
            return path, index
    return path, 0


def theme_fonts(theme: etree._Element, lang: str) -> dict[str, str]:
    """'+mj-lt', '+mn-ea', … → typeface; empty ea/cs slots are filled from the theme's font for the script."""
    out = {}
    for major, tag in (("mj", "majorFont"), ("mn", "minorFont")):
        node = theme.find(f".//{A}{tag}")
        if node is None:
            continue
        for kind, child in (("lt", "latin"), ("ea", "ea"), ("cs", "cs")):
            el = node.find(f"{A}{child}")
            out[f"+{major}-{kind}"] = el.get("typeface", "") if el is not None else ""
        script = node.find(f"{A}font[@script='{SCRIPT_TAG.get(lang, '-')}']")
        if script is not None:
            for kind in ("ea", "cs"):
                if not out.get(f"+{major}-{kind}"):
                    out[f"+{major}-{kind}"] = script.get("typeface", "")
    return out
