"""Protected tokens: identifiers that must appear unchanged in the translation.

Two strategies (chosen per engine/run):
- verify: leave tokens in the text so the model has full context, then check they survived (default).
- mask:   replace opaque tokens (URLs, e-mails, IPs, paths, part numbers) with <x1/> placeholders and restore.
"""
from __future__ import annotations

import re
import unicodedata

_OPAQUE = [
    r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+",
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?(?:/\d{1,2})?\b",
    r"[A-Za-z]:\\(?:[^\\<>\n\u3000-\u9fff\uff00-\uffef]+?\\)*[^\\\s<>\u3000-\u9fff\uff00-\uffef]*",  # Windows paths
    r"\b[A-Z]{1,6}-[A-Z0-9]*\d[A-Z0-9]*(?:-[A-Z0-9]+)*\b",       # part/model numbers: FX-PCG2611-0
    r"\bv\d+(?:\.\d+)+\b",                                        # versions
    r"\b(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?::\d+)?(?:/[^\s<>]*)?\b(?=[^.\w]|$)",  # host names: mqtt.example.com:8883
]
_ACRONYM = r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9]*[A-Z0-9](?:/[A-Z]{2,})?(?![A-Za-z0-9])"   # BMS, CO2, BACnet, TCP/IP
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

OPAQUE_RE = re.compile("|".join(f"(?:{p})" for p in _OPAQUE))
ACRONYM_RE = re.compile(_ACRONYM)
_FULLWIDTH_ALNUM = re.compile(r"[\uff21-\uff3a\uff41-\uff5a\uff10-\uff19]")


def _trim(token: str) -> str:
    """Sentence punctuation after a URL is not part of it; neither is an unbalanced closing bracket:
    "(see https://x.example.com/a)." → https://x.example.com/a"""
    token = token.rstrip(".,;:'")
    while token.endswith(")") and token.count(")") > token.count("("):
        token = token[:-1].rstrip(".,;:")
    return token


def protected_tokens(text: str, dnt_terms: list[str]) -> list[str]:
    """Tokens from `text` that must appear verbatim in the translation."""
    found: list[str] = [_trim(m.group(0)) for m in OPAQUE_RE.finditer(text)]
    for m in ACRONYM_RE.finditer(text):
        tok = m.group(0)
        if sum(c.isupper() for c in tok) >= 2 and not any(tok in f for f in found):
            found.append(tok)
    found.extend(t for t in dnt_terms if t not in found)
    return list(dict.fromkeys(found))


# Native digits (Burmese, Thai, full-width, Arabic-Indic) → ASCII, so "၂၀၂၆" and "2026" compare equal.
_NATIVE_DIGITS = str.maketrans({**{chr(0x1040 + i): str(i) for i in range(10)},
                                **{chr(0x0E50 + i): str(i) for i in range(10)},
                                **{chr(0xFF10 + i): str(i) for i in range(10)},
                                **{chr(0x0660 + i): str(i) for i in range(10)}})


def significant_numbers(text: str) -> set[str]:
    """Numbers that should survive translation (≥2 digits or decimals; single digits are too ambiguous)."""
    nums = {n.replace(",", "") for n in _NUMBER.findall(text.translate(_NATIVE_DIGITS))}
    return {n for n in nums if len(n.replace(".", "")) >= 2 or "." in n}


def normalize_fullwidth(text: str) -> str:
    """ＢＭＳ → BMS, ２４ → 24. Leaves Japanese punctuation such as （） and 、 untouched."""
    return _FULLWIDTH_ALNUM.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), text)


_LATIN_TARGETS = {"en", "de", "fr", "es"}
_FW_PUNCT_TO_ASCII = str.maketrans({"（": "(", "）": ")", "～": "–", "〜": "–", "，": ", ", "；": "; "})


_COMPAT = re.compile(r"[\uf900-\ufaff\u2f00-\u2fdf]")      # compatibility ideographs, Kangxi radicals
_FULLWIDTH_FORMS = re.compile(r"[\uff01-\uff5e\u3000]")
# a space between two Japanese/Chinese characters (incl. 、。「」（）) is never correct
_CJK_GAP = re.compile(r"(?<=[\u3000-\u30ff\u4e00-\u9fff\uff00-\uffef])[ \t]+(?=[\u3000-\u30ff\u4e00-\u9fff\uff00-\uffef])")


def tidy(source: str, output: str, tgt: str) -> str:
    """Deterministic clean-up after translation. Keeps the source document's own notation for units."""
    # Models sometimes emit look-alike code points (年 as U+F98E): map them to the standard character.
    out = _COMPAT.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), output)
    if tgt in ("ja", "zh", "ko"):
        out = normalize_fullwidth(out)
    if tgt in ("ja", "zh"):
        out = _CJK_GAP.sub("", out)
    if "％" in out and "％" not in source:
        out = out.replace("％", "%")
    if tgt in ("ja", "zh", "ko"):
        out = re.sub(r"\s?°\s?C", "℃", out)     # CJK fonts draw "°" full-width: use the single ℃ character
    elif "℃" in out and "℃" not in source and "°C" in source:
        out = re.sub(r"\s?℃", " °C" if " °C" in source else "°C", out)
    if tgt in _LATIN_TARGETS:
        out = out.translate(_FW_PUNCT_TO_ASCII).replace("：", ": ")
        out = _FULLWIDTH_FORMS.sub(lambda m: unicodedata.normalize("NFKC", m.group(0)), out).replace("  ", " ")
        m = re.match(r"^((?:<g\d+>)?)([a-z])", out)
        if m and not re.match(r"^(?:<g\d+>)?[a-z]+[A-Z0-9]", out):   # don't touch identifiers like "iPhone"
            out = m.group(1) + m.group(2).upper() + out[m.end():]
    return out


def restore_parentheses(source: str, output: str, tokens: list[str], tgt: str) -> str:
    """Deterministic repair: '(VAV)' in the source but bare 'VAV' in the output → re-add the brackets.
    Asking the model to fix this made translations worse in testing, so it is done in code."""
    out = re.sub(r"([（(])\s*[（(](.+?)[）)]\s*([）)])", r"\1\2\3", output)          # ((EMS)) → (EMS)
    open_b, close_b = ("（", "）") if tgt in ("ja", "zh", "ko") else (" (", ")")
    for t in parenthesised(source, tokens):
        if t in out and not parenthesised(out, [t]):
            out = re.sub(rf"\s*(?<![A-Za-z0-9]){re.escape(t)}(?![A-Za-z0-9])", f"{open_b}{t}{close_b}", out, count=1)
    return out


def parenthesised(text: str, tokens: list[str]) -> list[str]:
    """Protected tokens that appear inside parentheses in `text`, e.g. 'Variable Air Volume (VAV)'."""
    return [t for t in tokens if re.search(rf"[（(]\s*{re.escape(t)}\s*[）)]", text)]


def mask(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        key = f"<x{len(mapping) + 1}/>"
        mapping[key] = m.group(0)
        return key
    return OPAQUE_RE.sub(repl, text), mapping


def unmask(text: str, mapping: dict[str, str]) -> str:
    for key, value in mapping.items():
        text = text.replace(key, value)
    return text
