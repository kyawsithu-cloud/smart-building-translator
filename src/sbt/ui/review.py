"""Review screen: list paragraphs side by side, accept user edits, explain problems in plain words.

Formatting tags are shown to the user as [1]…[/1] (easier to read and type than <g1>…</g1>).
Problems come from the independent quality checks (sbt.quality), so Review, the result screen and the
report agree.
"""
from __future__ import annotations

import re

from sbt.app.jobs import TranslationJob
from sbt.domain.models import Severity
from sbt.pipeline.tags import is_well_formed, tag_counts
from sbt.protection import tokens as tok
from sbt.quality import completeness, identifiers, terminology
from sbt.quality.context import pairs
from sbt.quality.findings import CATEGORIES, Finding

_TAG = re.compile(r"<(/?)g(\d+)>")
_SHOWN = re.compile(r"\[(/?)(\d+)\]")


def to_display(text: str) -> str:
    return _TAG.sub(lambda m: f"[{m.group(1)}{m.group(2)}]", text)


def from_display(text: str, allowed: set[int]) -> str:
    """[1]…[/1] back to <g1>…</g1>, only for tag numbers that exist in the source paragraph."""
    return _SHOWN.sub(lambda m: f"<{m.group(1)}g{m.group(2)}>" if int(m.group(2)) in allowed else m.group(0), text)


def finding_view(f: Finding, index: int) -> dict[str, object]:
    out: dict[str, object] = {"index": index, "category": f.category, "category_label": CATEGORIES[f.category],
                              "code": f.code, "severity": f.severity.value, "text": f.describe(),
                              "message": f.message, "segments": f.segments, "pages": f.pages}
    if f.code == "term_variants":
        variants = f.detail.get("variants") or {}
        out["variants"] = [{"text": v, "count": len(ids)} for v, ids in variants.items()]  # type: ignore[union-attr]
        out["majority"] = f.detail.get("majority", "")
        out["term"] = f.detail.get("term", "")
    if f.code == "same_source_differs":
        variants = f.detail.get("variants") or {}
        out["variants"] = [{"text": v, "count": len(ids)} for v, ids in variants.items()]  # type: ignore[union-attr]
    return out


def findings(job: TranslationJob) -> list[dict[str, object]]:
    return [finding_view(f, i) for i, f in enumerate(job.quality.sorted())]


def items(job: TranslationJob) -> list[dict[str, object]]:
    out = []
    outcomes = job.result.outcomes if job.result else {}
    per_segment = job.quality.by_segment()
    for s in job.doc.segments:
        o = outcomes.get(s.id)
        status = "edited" if s.id in job.edited else (o.status if o else "")
        checks = [{"category": f.category, "code": f.code, "severity": f.severity.value, "text": f.describe()}
                  for f in sorted(per_segment.get(s.id, []), key=lambda f: f.severity != Severity.ERROR)]
        out.append({
            "id": s.id, "page": s.container, "kind": s.kind.value, "status": status,
            "checks": checks, "categories": sorted({c["category"] for c in checks if c["severity"] != "info"}),
            "flagged": any(c["severity"] != "info" for c in checks),
            "ocr": s.ocr_confidence is not None,
            "source": to_display(s.source), "translation": to_display(s.translation or ""),
            "has_tags": bool(s.tag_ids),
        })
    return out


def segment_checks(job: TranslationJob, segment_id: str, tagged: str) -> list[Finding]:
    """Per-paragraph quality checks of a proposed translation (the document is left unchanged)."""
    seg = next(s for s in job.doc.segments if s.id == segment_id)
    before = seg.translation
    seg.translation = tagged
    try:
        p = next(x for x in pairs(job.doc, job.spec.source_lang, job.spec.target_lang, job.glossary)
                 if x.seg.id == segment_id)
        if p.kept:
            return []
        found = [f for f in completeness.check([p], job.doc, job.spec.source_lang, job.spec.target_lang)
                 if f.segments] + identifiers.check([p]) + terminology.check([p], job.spec.target_lang, None)
        return found
    finally:
        seg.translation = before


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
    warnings += [f.describe() + "." for f in segment_checks(job, segment_id, text)]
    return text, warnings


def strip_display_tags(text: str) -> str:
    return _TAG.sub("", text)
