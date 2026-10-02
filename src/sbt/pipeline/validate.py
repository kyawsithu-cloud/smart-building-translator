"""Per-segment validation of a model output. Returns problems; the pipeline decides whether to retry."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sbt import languages
from sbt.pipeline.tags import is_well_formed, strip_tags, tag_counts, tag_ids
from sbt.protection.tokens import parenthesised, significant_numbers
from sbt.terminology.glossary import Hint

# number_mismatch became retryable in Phase 2 after "210 MWh" turned into "2.1亿千瓦时" (×1000) in Chinese.
RETRYABLE = {"empty", "tags", "placeholders", "token_missing", "term_missing", "untranslated", "foreign_script",
             "number_mismatch", "added_text"}
_SCRIPTS = {
    "Korean": re.compile(r"[\uac00-\ud7af\u1100-\u11ff]"),
    "Japanese kana": re.compile(r"[\u3040-\u30ff]"),
    "Chinese/Japanese kanji": re.compile(r"[\u2e80-\u2fdf\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"),
    "Thai": re.compile(r"[\u0e00-\u0e7f]"),
    "Burmese": re.compile(r"[\u1000-\u109f]"),
    "Cyrillic": re.compile(r"[\u0400-\u04ff]"),
    "Arabic": re.compile(r"[\u0600-\u06ff]"),
}
_ALLOWED = {"ja": {"Japanese kana", "Chinese/Japanese kanji"}, "zh": {"Chinese/Japanese kanji"},
            "ko": {"Korean", "Chinese/Japanese kanji"}, "th": {"Thai"}, "my": {"Burmese"}}


def _wide(text: str) -> bool:
    """Any East-Asian wide character: in English/German/French/Spanish output it is always a leftover,
    whatever code point the model used (Latin fonts cannot draw these; they show as boxes)."""
    return any(unicodedata.east_asian_width(c) in ("W", "F") for c in text)


def _foreign_scripts(source: str, output: str, tgt: str) -> list[str]:
    """Scripts in the output that belong neither to the target language nor to the source text."""
    allowed = _ALLOWED.get(tgt, set())
    return [name for name, rx in _SCRIPTS.items()
            if name not in allowed and rx.search(output) and not rx.search(source)]
_LATIN = {"en", "de", "fr", "es"}
_RATIO = {("en", "ja"): (0.2, 1.4), ("ja", "en"): (0.7, 5.0)}


@dataclass(frozen=True)
class Problem:
    code: str
    feedback: str        # sent back to the local model on retry (may quote tokens; never logged)
    count: int = 1


def validate(source: str, output: str, tokens: list[str], hints: tuple[Hint, ...],
             src: str, tgt: str, placeholders: list[str] | None = None) -> list[Problem]:
    problems: list[Problem] = []
    if not output.strip():
        return [Problem("empty", "The previous answer was empty.")]

    if tag_ids(source):
        if not is_well_formed(output) or tag_counts(output) != tag_counts(source):
            problems.append(Problem("tags", "The previous answer broke the formatting tags. Keep each <gN>…</gN> "
                                            "pair exactly once."))
    for ph in placeholders or []:
        if output.count(ph) != 1:
            problems.append(Problem("placeholders", f"Keep the placeholder {ph} exactly once."))

    plain = strip_tags(output)
    if output.count("\n") > source.count("\n"):
        problems.append(Problem("added_text", "Translate only the given text, as one paragraph. Do not add other "
                                              "lines or headings."))
    missing = [t for t in tokens if t not in plain]
    if missing:
        problems.append(Problem("token_missing", "Keep these unchanged: " + ", ".join(missing), len(missing)))

    unbracketed = [t for t in parenthesised(strip_tags(source), tokens) if t in plain
                   and t not in parenthesised(plain, [t])]
    if unbracketed:
        problems.append(Problem("parentheses_lost", "Keep these in parentheses: " + ", ".join(
            f"({t})" for t in unbracketed), len(unbracketed)))

    stray = _foreign_scripts(strip_tags(source), plain, tgt)
    if stray:
        problems.append(Problem("foreign_script", "The previous answer contained characters from another "
                                                  f"language ({', '.join(stray)}). Use only {languages.get(tgt).name}.",
                                len(stray)))

    lower = plain.lower()
    bad_terms = [h for h in hints if not h.do_not_translate and h.target.lower() not in lower]
    if bad_terms:
        problems.append(Problem("term_missing", "Use these required terms: " + "; ".join(
            f"{h.source} → {h.target}" for h in bad_terms), len(bad_terms)))

    tgt_lang = languages.get(tgt)
    src_lang = languages.get(src)
    residue = plain
    for t in tokens:
        residue = residue.replace(t, "")
    latin_target = tgt in _LATIN
    if not latin_target and not tgt_lang.script.search(residue):          # e.g. en→ja with no Japanese
        problems.append(Problem("untranslated", f"The text was not translated into {tgt_lang.name}."))
    elif latin_target and src not in _LATIN and (src_lang.script.search(residue) or _wide(residue)):
        problems.append(Problem("untranslated", "Part of the text was left untranslated."))   # e.g. ja→en leftovers
    elif latin_target and src in _LATIN and plain.strip() == strip_tags(source).strip():
        problems.append(Problem("untranslated", f"The text was not translated into {tgt_lang.name}."))

    src_nums = significant_numbers(strip_tags(source))
    tgt_nums = significant_numbers(plain)
    lost = src_nums - tgt_nums
    if lost:
        problems.append(Problem("number_mismatch", "Keep every number and unit exactly as in the source text: "
                                + ", ".join(sorted(lost)) + ".", len(lost)))

    src_plain = strip_tags(source)
    lo, hi = _RATIO.get((src, tgt), (0.25, 4.0))
    if len(src_plain) >= 40 and not lo <= len(plain) / len(src_plain) <= hi:
        problems.append(Problem("length_suspicious", ""))
    return problems
