"""Offline language detection for the supported languages (no model, no network).

Script decides most cases (kana → ja, Hangul → ko, Thai, Burmese, Han without kana → zh). Latin-script
languages are separated by counting very common function words.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_SCRIPTS = {
    "kana": re.compile(r"[\u3040-\u30ff]"),
    "han": re.compile(r"[\u4e00-\u9fff]"),
    "hangul": re.compile(r"[\uac00-\ud7af]"),
    "thai": re.compile(r"[\u0e00-\u0e7f]"),
    "myanmar": re.compile(r"[\u1000-\u109f]"),
    "latin": re.compile(r"[A-Za-z\u00c0-\u00ff]"),
}
_FUNCTION_WORDS = {
    "en": "the and of to in is for with on are by this that from be as or at an it which".split(),
    "de": "der die das und ist mit für von den des ein eine nicht zu im auf dem wird sind auch".split(),
    "fr": "le la les et des est pour avec une dans du en sur au par sont ce qui pas aux".split(),
    "es": "el la los las y es para con una en del que por se al son como su más".split(),
}
_WORD = re.compile(r"[a-z\u00e0-\u00ff\u00e4\u00f6\u00fc\u00df]+")


@dataclass(frozen=True)
class Detection:
    language: str
    confidence: float      # 0–1, share of evidence for the winning language


def detect(text: str) -> Detection:
    counts = {name: len(rx.findall(text)) for name, rx in _SCRIPTS.items()}
    total = sum(counts.values()) or 1
    if counts["kana"] > 0 and counts["kana"] + counts["han"] >= 0.2 * total:
        return Detection("ja", (counts["kana"] + counts["han"]) / total)
    for script, lang in (("hangul", "ko"), ("thai", "th"), ("myanmar", "my"), ("han", "zh")):
        if counts[script] >= 0.2 * total:
            return Detection(lang, counts[script] / total)
    words = Counter(_WORD.findall(text.lower()))
    scores = {lang: sum(words[w] for w in ws) for lang, ws in _FUNCTION_WORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    hits = sum(scores.values())
    if hits == 0:          # bullet-only decks: no function words; English is the safest default
        return Detection("en", 0.5)
    return Detection(best, scores[best] / hits)


def default_target(source: str, preferred: str = "") -> str:
    """The user's usual target language when set (and different from the source); otherwise English ↔ Japanese,
    and other languages to English."""
    if preferred and preferred != source:
        return preferred
    return {"en": "ja", "ja": "en"}.get(source, "en")
