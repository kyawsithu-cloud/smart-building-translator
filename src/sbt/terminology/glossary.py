"""Terminology dictionary: matching.

Entries are stored in one direction (e.g. en→ja) and used in both: for ja→en the target term is matched in the
source text and the source term is suggested. Do-not-translate (DNT) entries apply to every language pair.

Context-dependent entries: an entry with `context` (comma-separated keywords) is used only when one of the
keywords occurs in the surrounding text (the slide). It then wins over the entry without context for the
same term. Among otherwise equal candidates, higher `priority` wins.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}
CSV_FIELDS = ["source_term", "target_term", "source_lang", "target_lang", "category", "notes",
              "do_not_translate", "priority", "context"]


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

    @property
    def context_keywords(self) -> list[str]:
        return [k.strip().lower() for k in self.context.split(",") if k.strip()]


@dataclass(frozen=True)
class Hint:
    """A term found in a segment and what it must become in the target language.

    origin: "glossary" (user-approved, enforced) or "document" (term sheet, see term_sheet.py).
    """
    source: str
    target: str
    do_not_translate: bool
    origin: str = "glossary"


def read_csv(path: Path) -> list[Term]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [Term(
            source_term=row["source_term"].strip(), target_term=(row.get("target_term") or "").strip(),
            source_lang=row["source_lang"].strip(), target_lang=row["target_lang"].strip(),
            category=(row.get("category") or "").strip(), notes=(row.get("notes") or "").strip(),
            do_not_translate=(row.get("do_not_translate") or "").strip().lower() in ("true", "1", "yes"),
            priority=(row.get("priority") or "normal").strip().lower() or "normal",
            context=(row.get("context") or "").strip(),
        ) for row in csv.DictReader(f) if (row.get("source_term") or "").strip()]


def write_csv(path: Path, terms: list[Term]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for t in terms:
            w.writerow({**t.__dict__, "do_not_translate": "true" if t.do_not_translate else "false"})


@dataclass(frozen=True)
class _Pattern:
    regex: re.Pattern[str]
    hint: Hint
    keywords: tuple[str, ...]
    priority: int
    length: int


class Glossary:
    def __init__(self, terms: list[Term], name: str = "") -> None:
        self.terms = terms
        self.name = name
        self._cache: dict[tuple[str, str], list[_Pattern]] = {}

    @classmethod
    def load_csv(cls, path: Path) -> Glossary:
        return cls(read_csv(path), path.stem)

    def _patterns(self, src: str, tgt: str) -> list[_Pattern]:
        key = (src, tgt)
        if key in self._cache:
            return self._cache[key]
        out: list[_Pattern] = []
        for t in self.terms:
            if t.do_not_translate:
                text, hint = t.source_term, Hint(t.source_term, t.source_term, True)
            elif (t.source_lang, t.target_lang) == (src, tgt):
                text, hint = t.source_term, Hint(t.source_term, t.target_term, False)
            elif (t.target_lang, t.source_lang) == (src, tgt):
                text, hint = t.target_term, Hint(t.target_term, t.source_term, False)
            else:
                continue
            out.append(_Pattern(term_regex(text), hint, tuple(t.context_keywords),
                                PRIORITY_ORDER.get(t.priority, 1), len(text)))
        # Longest match first; then context-specific before generic; then priority.
        out.sort(key=lambda p: (-p.length, 0 if p.keywords else 1, p.priority))
        self._cache[key] = out
        return out

    def match(self, text: str, src: str, tgt: str, context_text: str = "") -> list[Hint]:
        """Non-overlapping hints for terms in `text`. `context_text` (e.g. the whole slide) selects
        context-dependent entries; `text` itself always counts as context."""
        around = f"{text}\n{context_text}".lower()
        taken: list[tuple[int, int]] = []
        hints: list[Hint] = []
        for p in self._patterns(src, tgt):
            if p.keywords and not any(k in around for k in p.keywords):
                continue
            for m in p.regex.finditer(text):
                if any(m.start() < e and s < m.end() for s, e in taken):
                    continue
                taken.append((m.start(), m.end()))
                if p.hint not in hints:
                    hints.append(p.hint)
        return hints

    def covers(self, phrase: str, src: str, tgt: str) -> bool:
        """True if the glossary already has an entry for this exact phrase (any context)."""
        return any(p.regex.fullmatch(phrase) for p in self._patterns(src, tgt))


def inject(text: str, hints: list[Hint] | tuple[Hint, ...]) -> str:
    """Replace source terms with their approved target terms before translation.

    Used as the retry strategy when a model ignored terminology hints: the model then only has to translate
    the words around the (already correct) term. Tags like <g1> are never touched because terms don't match them.
    """
    for h in sorted((h for h in hints if not h.do_not_translate), key=lambda h: -len(h.source)):
        text = term_regex(h.source).sub(lambda m, t=h.target: t, text)
    return text


def term_regex(term: str) -> re.Pattern[str]:
    escaped = re.escape(term)
    if term.isascii():
        flags = 0 if term.isupper() or any(c.isdigit() for c in term) else re.IGNORECASE
        return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?:s|es)?(?![A-Za-z0-9])", flags)
    return re.compile(escaped)
