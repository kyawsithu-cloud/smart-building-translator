"""Quality control: independent checks of a finished translation (Phase 5).

Runs on the final state of every paragraph (after retries, repair and the user's own corrections) and on the
written file, not on the pipeline's bookkeeping. Used after each translation, after Review edits, and to check
a translation made elsewhere (sbt.quality.compare).

  terminology    glossary terms, recurring terms worded differently, same text translated differently
  completeness   not translated, partly translated, likely omissions, not written to the file, pictures
  identifiers    URLs, IPs, e-mails, part numbers, acronyms, numbers and units
  layout         text overflow, reduced fonts, titles wrapping, simplified formatting, fonts and glyphs
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from sbt.domain.models import DocumentModel, Issue, Severity
from sbt.quality import completeness, identifiers, output_check, terminology
from sbt.quality import fonts as font_check
from sbt.quality.context import pairs
from sbt.quality.findings import CATEGORIES, Finding, QcReport
from sbt.terminology.glossary import Glossary
from sbt.terminology.term_sheet import TermSheet

__all__ = ["CATEGORIES", "Finding", "QcReport", "check"]
_NUM = re.compile(r"(?:slide|page) (\d+)")
_LAYOUT = {"overflow": Severity.WARNING, "font_reduced": Severity.INFO, "extra_lines": Severity.INFO,
           "box_grows": Severity.INFO, "overflow_inherited": Severity.INFO}


def _layout(doc: DocumentModel, render_issues: list[Issue]) -> list[Finding]:
    by_shape: dict[str, list[str]] = defaultdict(list)
    for s in doc.segments:
        by_shape[s.shape_key].append(s.id)
    ids = {s.id for s in doc.segments}
    out = []
    for i in render_issues:
        segs = [i.segment_id] if i.segment_id in ids else by_shape.get(i.segment_id or "", [])
        m = _NUM.search(i.message)
        out.append(Finding("layout", i.code, _LAYOUT.get(i.code, i.severity), i.message, segs,
                           [int(m.group(1))] if m else []))
    simplified = [s for s in doc.segments if s.formatting_simplified and s.translation is not None]
    if simplified:
        out.append(Finding("layout", "formatting_simplified", Severity.INFO,
                           f"{len(simplified)} paragraph(s) use one style instead of mixed formatting",
                           [s.id for s in simplified], sorted({s.container for s in simplified})))
    return out


def check(doc: DocumentModel, src: str, tgt: str, glossary: Glossary, *, sheet: TermSheet | None = None,
          output: Path | None = None, original: Path | None = None,
          render_issues: list[Issue] | None = None) -> QcReport:
    ps = pairs(doc, src, tgt, glossary)
    active = [p for p in ps if not p.kept and p.seg.translation is not None]
    findings = (completeness.check(ps, doc, src, tgt) + terminology.check(ps, tgt, sheet)
                + identifiers.check(ps) + _layout(doc, render_issues or []))
    checked = {
        "paragraphs": len(ps), "translated": len(active),
        "identifiers": sum(len(p.protected) for p in active),
        "glossary_terms": sum(1 for p in active for h in p.hints if not h.do_not_translate),
        "recurring_terms": len(sheet.all_terms) if sheet else 0,
    }
    if output is not None and output.exists():
        pdf = output.suffix.lower() == ".pdf"
        more, verified = output_check.check(doc, output, original,
                                            font_check.pdf_font_names(tgt) if pdf else ())
        findings += more
        checked["written_verified"] = verified
        if not pdf:
            findings += font_check.check_pptx(output, {s.id for s in doc.segments if s.translation is not None},
                                              tgt)
    return QcReport(findings, checked)
