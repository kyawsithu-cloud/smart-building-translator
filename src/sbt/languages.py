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


_CJK = r"぀-ヿ㐀-䶿一-鿿ｦ-ﾟ"

LANGUAGES: dict[str, Language] = {
    lang.code: lang for lang in [
        Language("en", "English", "en-US", re.compile(r"[A-Za-z]")),
        Language("ja", "Japanese", "ja-JP", re.compile(f"[{_CJK}]"), east_asian=True),
        Language("zh", "Chinese", "zh-CN", re.compile(r"[一-鿿]"), east_asian=True),
        Language("ko", "Korean", "ko-KR", re.compile(r"[가-힯]"), east_asian=True),
        Language("my", "Burmese", "my-MM", re.compile(r"[က-႟]"), complex_script=True),
        Language("th", "Thai", "th-TH", re.compile(r"[฀-๿]"), complex_script=True),
        Language("de", "German", "de-DE", re.compile(r"[A-Za-zÄÖÜäöüß]")),
        Language("fr", "French", "fr-FR", re.compile(r"[A-Za-zÀ-ÿ]")),
        Language("es", "Spanish", "es-ES", re.compile(r"[A-Za-zÁÉÍÑÓÚÜáéíñóúü]")),
    ]
}


def get(code: str) -> Language:
    try:
        return LANGUAGES[code]
    except KeyError:
        raise ValueError(f"Unsupported language '{code}'. Supported: {', '.join(LANGUAGES)}") from None
