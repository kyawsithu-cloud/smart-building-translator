"""Fonts for writing translated text into PDFs: Windows system fonts, chosen per target language.

Each family gives a regular and a bold file; serif variants are used when the original text was serif.
Fonts are embedded as subsets by PyMuPDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WINDOWS_FONTS = Path(r"C:\Windows\Fonts")

# language -> (sans regular, sans bold, serif regular, serif bold); first existing file wins per slot
_FAMILIES: dict[str, tuple[list[str], list[str], list[str], list[str]]] = {
    "ja": (["meiryo.ttc", "YuGothM.ttc", "msgothic.ttc"], ["meiryob.ttc", "YuGothB.ttc"],
           ["yumin.ttf", "msmincho.ttc"], ["yumindb.ttf"]),
    "zh": (["msyh.ttc", "simsun.ttc"], ["msyhbd.ttc"], ["simsun.ttc"], ["simsun.ttc"]),
    "ko": (["malgun.ttf"], ["malgunbd.ttf"], ["batang.ttc", "malgun.ttf"], ["malgunbd.ttf"]),
    "th": (["LeelawUI.ttf", "tahoma.ttf"], ["LeelaUIb.ttf", "tahomabd.ttf"], ["LeelawUI.ttf"], ["LeelaUIb.ttf"]),
    "my": (["mmrtext.ttf"], ["mmrtextb.ttf"], ["mmrtext.ttf"], ["mmrtextb.ttf"]),
    "*": (["arial.ttf"], ["arialbd.ttf"], ["times.ttf"], ["timesbd.ttf"]),
}


@dataclass(frozen=True)
class FontSet:
    sans: str
    sans_bold: str
    serif: str
    serif_bold: str

    def css(self) -> str:
        """@font-face rules; families 'sbt-sans' and 'sbt-serif' with real bold faces."""
        rules = []
        for family, regular, bold in (("sbt-sans", self.sans, self.sans_bold), ("sbt-serif", self.serif,
                                                                             self.serif_bold)):
            rules.append(f"@font-face {{font-family: {family}; src: url({regular});}}")
            rules.append(f"@font-face {{font-family: {family}; src: url({bold}); font-weight: bold;}}")
        return "\n".join(rules)


def _first(names: list[str], fallback: str) -> str:
    for n in names:
        if (WINDOWS_FONTS / n).exists():
            return n
    return fallback


def for_language(lang: str) -> FontSet:
    sans, sans_b, serif, serif_b = _FAMILIES.get(lang, _FAMILIES["*"])
    base = _FAMILIES["*"]
    s = _first(sans, _first(base[0], "arial.ttf"))
    return FontSet(s, _first(sans_b, s), _first(serif, s), _first(serif_b, _first(sans_b, s)))
