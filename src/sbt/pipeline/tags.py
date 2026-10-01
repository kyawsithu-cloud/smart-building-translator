"""Inline formatting tags: <g1>…</g1>. Parsing, stripping and validation."""
from __future__ import annotations

import re

TAG_RE = re.compile(r"</?g(\d+)>")
_SPAN_RE = re.compile(r"<g(\d+)>(.*?)</g\1>", re.S)


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text)


def tag_ids(text: str) -> set[int]:
    return {int(m.group(1)) for m in TAG_RE.finditer(text)}


def tag_counts(text: str) -> dict[int, int]:
    """How many times each tag id is opened: extra spans (e.g. a second <g1>) change formatting too."""
    counts: dict[int, int] = {}
    for m in re.finditer(r"<g(\d+)>", text):
        counts[int(m.group(1))] = counts.get(int(m.group(1)), 0) + 1
    return counts


def is_well_formed(text: str) -> bool:
    """Tags must be balanced and non-nested."""
    open_id: int | None = None
    for m in TAG_RE.finditer(text):
        closing = m.group(0).startswith("</")
        tid = int(m.group(1))
        if not closing:
            if open_id is not None:
                return False
            open_id = tid
        else:
            if open_id != tid:
                return False
            open_id = None
    return open_id is None


def retag(tagged_source: str, output: str, known: dict[str, str]) -> str | None:
    """Re-apply formatting tags to an untagged translation when each tagged span is a known item.

    `known` maps source text → the exact text it must appear as in the output (protected tokens map to
    themselves, glossary terms to their approved target). Returns None if any span cannot be located.
    """
    result = output
    for tid, span in split_spans(tagged_source):
        if tid is None:
            continue
        target = known.get(span.strip()) or known.get(span.strip().lower())
        if not target or target not in strip_tags(result):
            return None
        result = result.replace(target, f"<g{tid}>{target}</g{tid}>", 1)
    return result if is_well_formed(result) else None


def split_spans(text: str) -> list[tuple[int | None, str]]:
    """'a<g1>b</g1>c' -> [(None,'a'), (1,'b'), (None,'c')]. Assumes well-formed input."""
    spans: list[tuple[int | None, str]] = []
    pos = 0
    for m in _SPAN_RE.finditer(text):
        if m.start() > pos:
            spans.append((None, text[pos:m.start()]))
        spans.append((int(m.group(1)), m.group(2)))
        pos = m.end()
    if pos < len(text):
        spans.append((None, text[pos:]))
    return [s for s in spans if s[1]]
