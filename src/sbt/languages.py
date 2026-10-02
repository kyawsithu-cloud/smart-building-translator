"""Language registry. Adding a language = adding one entry here (plus model support)."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str                 # English name, used in prompts
    ooxml_lang: str           # value for a:rPr/@lang
    script: re.Pattern[str] | None   # characters that prove text is in this language's script
    east_asian: bool = False
    complex_script: bool = False


_CJK = r"\u2e80-\u2fdf\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f"  # incl. radicals + compatibility ideographs

LANGUAGES: dict[str, Language] = {
    lang.code: lang for lang in [
        Language("en", "English", "en-US", re.compile(r"[A-Za-z]")),
        Language("ja", "Japanese", "ja-JP", re.compile(f"[{_CJK}]"), east_asian=True),
        Language("zh", "Chinese", "zh-CN", re.compile(r"[\u2e80-\u2fdf\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"), east_asian=True),
        Language("ko", "Korean", "ko-KR", re.compile(r"[\uac00-\ud7af]"), east_asian=True),
        Language("my", "Burmese", "my-MM", re.compile(r"[\u1000-\u109f]"), complex_script=True),
        Language("th", "Thai", "th-TH", re.compile(r"[\u0e00-\u0e7f]"), complex_script=True),
        Language("de", "German", "de-DE", re.compile(r"[A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df]")),
        Language("fr", "French", "fr-FR", re.compile(r"[A-Za-z\u00c0-\u00ff]")),
        Language("es", "Spanish", "es-ES", re.compile(r"[A-Za-z\u00c1\u00c9\u00cd\u00d1\u00d3\u00da\u00dc\u00e1\u00e9\u00ed\u00f1\u00f3\u00fa\u00fc]")),
    ]
}


def get(code: str) -> Language:
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"Unsupported language '{code}'. Supported: {', '.join(LANGUAGES)}") from None
