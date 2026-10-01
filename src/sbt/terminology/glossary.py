"""Terminology dictionary: loading and matching.

Entries are stored in one direction (e.g. en→ja) and used in both: for ja→en the target term is matched in the
source text and the source term is suggested. Do-not-translate (DNT) entries apply to every language pair.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


@dataclass(frozen=True)
class Term:
    source_term: str
    target_term: str
    source_lang: str
    target_lang: str
    category: str = ""
    notes: str = ""
    do_not_translate: bool = False
    priority: str = "normal"
    context: str = ""


@dataclass(frozen=True)
class Hint:
    """A term found in a segment and what it must become in the target language."""
    source: str
    target: str
    do_not_translate: bool


class Glossary:
    def __init__(self, terms: list[Term]) -> None:
        self.terms = terms
        self._cache: dict[tuple[str, str], list[tuple[re.Pattern[str], Hint]]] = {}

    @classmethod
    def load_csv(cls, path: Path) -> Glossary:
        with path.open(encoding="utf-8-sig", newline="") as f:
            terms = [Term(
                source_term=row["source_term"].strip(), target_term=row["target_term"].strip(),
                source_lang=row["source_lang"].strip(), target_lang=row["target_lang"].strip(),
                category=row.get("category", ""), notes=row.get("notes", ""),
                do_not_translate=row.get("do_not_translate", "").strip().lower() in ("true", "1", "yes"),
                priority=row.get("priority", "normal").strip() or "normal", context=row.get("context", ""),
            ) for row in csv.DictReader(f) if row.get("source_term")]
        return cls(terms)

    def _patterns(self, src: str, tgt: str) -> list[tuple[re.Pattern[str], Hint]]:
        key = (src, tgt)
        if key in self._cache:
            return self._cache[key]
        pairs: list[tuple[str, Hint]] = []
        for t in self.terms:
            if t.do_not_translate:
                pairs.append((t.source_term, Hint(t.source_term, t.source_term, True)))
            elif (t.source_lang, t.target_lang) == (src, tgt):
                pairs.append((t.source_term, Hint(t.source_term, t.target_term, False)))
            elif (t.target_lang, t.source_lang) == (src, tgt):
                pairs.append((t.target_term, Hint(t.target_term, t.source_term, False)))
        pairs.sort(key=lambda p: -len(p[0]))          # longest match wins
        compiled = [(_term_regex(text), hint) for text, hint in pairs]
        self._cache[key] = compiled
        return compiled

    def match(self, text: str, src: str, tgt: str) -> list[Hint]:
        """Non-overlapping hints for terms occurring in `text`, longest first."""
        taken: list[tuple[int, int]] = []
        hints: list[Hint] = []
        for pattern, hint in self._patterns(src, tgt):
            for m in pattern.finditer(text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                if hint not in hints:
                    hints.append(hint)
        return hints


def inject(text: str, hints: list[Hint] | tuple[Hint, ...]) -> str:
    """Replace source terms with their approved target terms before translation.

    Used as the retry strategy when a model ignored terminology hints: the model then only has to translate
    the words around the (already correct) term. Tags like <g1> are never touched because terms don't match them.
    """
    for h in sorted((h for h in hints if not h.do_not_translate), key=lambda h: -len(h.source)):
        text = _term_regex(h.source).sub(lambda m, t=h.target: t, text)
    return text


def _term_regex(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if term.isascii():
        flags = 0 if term.isupper() or any(c.isdigit() for c in term) else re.IGNORECASE
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?:s|es)?(?![A-Za-z0-9])", flags)
    return re.compile(escaped)
