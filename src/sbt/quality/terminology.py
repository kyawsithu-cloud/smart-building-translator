"""Terminology consistency.

  glossary_term        an approved glossary term is in the source but its approved translation is not used
  term_variants        a recurring document term is worded differently across the document
                       (e.g. Building Management System → ビル管理システム on slide 1, 建物管理システム on slide 8)
  same_source_differs  the same paragraph (title, label, sentence) is translated differently in different places
"""
from __future__ import annotations

import re
from collections import defaultdict

from sbt.domain.models import Severity
from sbt.quality.context import Pair, norm
from sbt.quality.findings import Finding
from sbt.terminology import term_sheet as ts
from sbt.terminology.term_sheet import TermSheet

OTHER = "(other wording)"
_TRAILING = re.compile(r"[\s.。:：;；,，、!！?？]+$")
_HAS_WORD = re.compile(r"[^\W\d_]", re.UNICODE)


def _pages(ps: list[Pair]) -> list[int]:
    return sorted({p.seg.container for p in ps})


def _glossary(pairs: list[Pair], tgt: str) -> list[Finding]:
    missing: dict[tuple[str, str], list[Pair]] = defaultdict(list)
    used: dict[tuple[str, str], int] = defaultdict(int)
    for p in pairs:
        for h in p.hints:
            if h.do_not_translate or h.origin != "glossary":
                continue
            key = (h.source.lower(), h.target)
            if ts.contains(p.target, h.target, tgt):
                used[key] += 1
            else:
                missing[key].append(p)
    out = []
    for (source, target), ps in missing.items():
        total = len(ps) + used[(source, target)]
        out.append(Finding("terminology", "glossary_term", Severity.WARNING,
                           f"approved glossary term not used in {len(ps)} of {total} paragraph(s)",
                           [p.seg.id for p in ps], _pages(ps),
                           detail={"term": source, "approved": target}))
    return out


def _variant(text: str, candidates: list[str], tgt: str) -> str:
    for c in sorted(candidates, key=len, reverse=True):
        if ts.contains(text, c, tgt):
            return c
    return OTHER


def _recurring(pairs: list[Pair], sheet: TermSheet, tgt: str) -> list[Finding]:
    by_id = {p.seg.id: p for p in pairs}
    out = []
    for term in sheet.all_terms:
        ps = [by_id[i] for i in sorted(term.segments) if i in by_id and by_id[i].target.strip()]
        if len(ps) < 2 or not term.candidates:
            continue
        majority = term.target or ts.vote(term, [p.target for p in ps], tgt)
        candidates = list(dict.fromkeys(([majority] if majority else []) + term.candidates))
        groups: dict[str, list[Pair]] = defaultdict(list)
        for p in ps:
            groups[majority if majority and ts.contains(p.target, majority, tgt)
                   else _variant(p.target, candidates, tgt)].append(p)
        if majority:
            deviating = [p for v, g in groups.items() if v != majority for p in g]
            if not deviating:
                continue
            known_other = any(v not in (majority, OTHER) for v in groups)
            out.append(Finding("terminology", "term_variants", Severity.WARNING if known_other else Severity.INFO,
                               f"recurring term worded differently in {len(deviating)} of {len(ps)} paragraphs",
                               [p.seg.id for p in deviating], _pages(deviating),
                               detail={"term": term.source, "majority": majority,
                                       "variants": {v: [p.seg.id for p in g] for v, g in groups.items()}}))
        elif len([v for v in groups if v != OTHER]) >= 2:
            out.append(Finding("terminology", "term_variants", Severity.WARNING,
                               f"recurring term translated {len(groups)} different ways",
                               [p.seg.id for p in ps], _pages(ps),
                               detail={"term": term.source, "majority": "",
                                       "variants": {v: [p.seg.id for p in g] for v, g in groups.items()}}))
    return out


def _key(text: str, latin: bool) -> str:
    t = _TRAILING.sub("", norm(text))
    return t.casefold() if latin else t.replace(" ", "")


def _same_source(pairs: list[Pair], tgt: str) -> list[Finding]:
    groups: dict[str, list[Pair]] = defaultdict(list)
    for p in pairs:
        if p.kept or not p.target.strip() or not _HAS_WORD.search(p.source):
            continue
        groups[_key(p.source, True)].append(p)
    latin = tgt in ("en", "de", "fr", "es")
    out = []
    for ps in groups.values():
        if len(ps) < 2:
            continue
        variants: dict[str, list[Pair]] = defaultdict(list)
        for p in ps:
            variants[_key(p.target, latin)].append(p)
        if len(variants) < 2:
            continue
        shown = {v[0].target: [p.seg.id for p in v] for v in variants.values()}
        out.append(Finding("terminology", "same_source_differs", Severity.WARNING,
                           f"the same text is translated {len(variants)} different ways",
                           [p.seg.id for p in ps], _pages(ps),
                           detail={"source": ps[0].source, "variants": shown}))
    return out


def check(pairs: list[Pair], tgt: str, sheet: TermSheet | None) -> list[Finding]:
    active = [p for p in pairs if not p.kept and p.target.strip()]
    found = _glossary(active, tgt) + _same_source(active, tgt)
    if sheet is not None:
        found += _recurring(active, sheet, tgt)
    return found
