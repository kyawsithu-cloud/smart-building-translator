"""Job outputs next to the translated file.

  <name>.report.json  metrics + warnings — no document text
  <name>.review.csv   source/translation side by side — contains document text
  <name>.terms.csv    document term sheet in glossary format — contains document terms
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from sbt.domain.models import DocumentModel, Issue
from sbt.pipeline.translator import PipelineResult
from sbt.terminology.glossary import write_csv


def pct(hit: int, total: int) -> float | None:
    return round(100 * hit / total, 1) if total else None


def build(doc: DocumentModel, result: PipelineResult, render_issues: list[Issue],
          meta: dict[str, object]) -> dict[str, object]:
    statuses = [o.status for o in result.outcomes.values()]
    tagged = [s for s in doc.segments if s.tag_ids]
    translated = sum(s.translation is not None for s in doc.segments)
    return {
        **meta,
        "slides": doc.container_count, "segments": len(doc.segments), "translated_segments": translated,
        "status_counts": {k: statuses.count(k) for k in sorted(set(statuses))},
        "translated_pct": pct(translated, len(doc.segments)),
        "protected_token_integrity_pct": pct(result.token_hits, result.token_checks),
        "glossary_adherence_pct": pct(result.term_hits, result.term_checks),
        "doc_terms": len(result.term_sheet.terms) if result.term_sheet else 0,
        "doc_terms_unresolved": sum(1 for t in result.term_sheet.all_terms if not t.target and t.candidates)
        if result.term_sheet else 0,
        "harmonised": result.harmonised,
        "repair_tried": result.repair_tried,
        "doc_term_consistency_pct": pct(result.doc_term_hits, result.doc_term_checks),
        "tag_integrity_pct": pct(sum(not s.formatting_simplified for s in tagged), len(tagged)),
        "untranslatable": doc.untranslatable,
        "notices": doc.notices,
        "ocr_segments": sum(s.ocr_confidence is not None for s in doc.segments),
        "issues": [{"code": i.code, "severity": i.severity.value, "segment": i.segment_id, "message": i.message}
                   for i in result.issues + render_issues],
    }


def write_all(output: Path, doc: DocumentModel, result: PipelineResult, report: dict[str, object]) -> None:
    output.with_suffix(".report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                  encoding="utf-8")
    with output.with_suffix(".review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page/slide", "segment", "kind", "status", "problems", "ocr_confidence", "source",
                    "translation"])
        for s in doc.segments:
            o = result.outcomes.get(s.id)
            w.writerow([s.container, s.id, s.kind.value, o.status if o else "",
                        ";".join(o.problems) if o else "", "" if s.ocr_confidence is None else s.ocr_confidence,
                        s.source, s.translation or ""])
    if result.term_sheet and result.term_sheet.as_terms():
        write_csv(output.with_suffix(".terms.csv"), result.term_sheet.as_terms())
