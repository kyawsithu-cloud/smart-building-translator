"""Review screen: list paragraphs side by side, accept user edits, explain problems in plain words.

Formatting tags are shown to the user as [1]…[/1] (easier to read and type than <g1>…</g1>).
"""
from __future__ import annotations

import re

from sbt.app.jobs import TranslationJob
from sbt.pipeline.tags import is_well_formed, tag_counts
from sbt.pipeline.validate import validate
from sbt.protection import tokens as tok

_TAG = re.compile(r"<(/?)g(\d+)>")
_SHOWN = re.compile(r"\[(/?)(\d+)\]")

PROBLEM_TEXT = {
    "term_missing": "a required glossary term is missing",
    "token_missing": "an identifier (URL, IP, part number, acronym) changed",
    "untranslated": "not translated",
    "empty": "no translation",
    "tags": "formatting could not be kept",
    "foreign_script": "characters from another language",
    "number_mismatch": "a number may have changed",
    "length_suspicious": "unusually short or long (possible omission)",
    "parentheses_lost": "brackets around an acronym were dropped",
    "added_text": "the model added text",
    "placeholders": "a protected placeholder was lost",
}


def to_display(text: str) -> str:
    return _TAG.sub(lambda m: f"[{m.group(1)}{m.group(2)}]", text)


def from_display(text: str, allowed: set[int]) -> str:
    """[1]…[/1] back to <g1>…</g1>, only for tag numbers that exist in the source paragraph."""
    return _SHOWN.sub(lambda m: f"<{m.group(1)}g{m.group(2)}>" if int(m.group(2)) in allowed else m.group(0), text)


def items(job: TranslationJob) -> list[dict[str, object]]:
    out = []
    outcomes = job.result.outcomes if job.result else {}
    for s in job.doc.segments:
        o = outcomes.get(s.id)
        status = "edited" if s.id in job.edited else (o.status if o else "")
        problems = [] if s.id in job.edited else (list(o.problems) if o else [])
        out.append({
            "id": s.id, "page": s.container, "kind": s.kind.value, "status": status,
            "problems": problems, "problem_text": [PROBLEM_TEXT.get(p, p) for p in problems],
            "flagged": bool(problems) or status in ("failed", "simplified"),
            "ocr": s.ocr_confidence is not None,
            "source": to_display(s.source), "translation": to_display(s.translation or ""),
            "has_tags": bool(s.tag_ids),
        })
    return out


def check_edit(job: TranslationJob, segment_id: str, shown_text: str) -> tuple[str, list[str]]:
    """Convert and check an edit. Returns (tagged text, warnings). Warnings do not block saving: the user
    is the final authority, but should see what the automatic checks think."""
    seg = next(s for s in job.doc.segments if s.id == segment_id)
    text = tok.tidy(seg.source, from_display(shown_text.strip(), set(seg.tag_ids)), job.spec.target_lang)
    warnings = []
    if seg.tag_ids and (not is_well_formed(text) or tag_counts(text) != tag_counts(seg.source)):
        warnings.append("Formatting markers [n]…[/n] do not match the original; the paragraph will use one "
                        "style.")
        text = _TAG.sub("", text)
    protected = tok.protected_tokens(seg.plain_source, [])
    hints = tuple(job.glossary.match(seg.plain_source, job.spec.source_lang, job.spec.target_lang))
    for p in validate(seg.source if seg.tag_ids and "<g" in text else _TAG.sub("", seg.source), text, protected,
                      hints, job.spec.source_lang, job.spec.target_lang):
        if p.code != "tags":
            warnings.append(PROBLEM_TEXT.get(p.code, p.code).capitalize() + ".")
    return text, warnings
