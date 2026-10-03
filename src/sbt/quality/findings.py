"""Quality-control findings.

`message` never contains document text: it goes to `.report.json` and may be logged. `detail` may contain
document text (terms, variants, words left untranslated); it is shown in the app and written to the review
sheet only.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sbt.domain.models import Severity

CATEGORIES = {
    "terminology": "Terminology consistency",
    "completeness": "Missing or partial translation",
    "identifiers": "Identifiers and numbers",
    "layout": "Layout and fonts",
}
_RANK = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass
class Finding:
    category: str
    code: str
    severity: Severity
    message: str                                         # no document text
    segments: list[str] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)
    detail: dict[str, object] = field(default_factory=dict)   # may contain document text

    def public(self) -> dict[str, object]:
        return {"category": self.category, "code": self.code, "severity": self.severity.value,
                "message": self.message, "segments": self.segments, "pages": self.pages}

    def describe(self) -> str:
        """One sentence for the person reviewing (may quote document text; shown in the app only)."""
        d = self.detail
        q = "“{}”".format
        texts = {
            "glossary_term": lambda: f"Glossary: {q(d['term'])} should be {q(d['approved'])}",
            "term_variants": lambda: (f"{q(d['term'])} is {q(d['majority'])} in most places"
                                      if d.get("majority") else f"{q(d['term'])} is translated differently"),
            "same_source_differs": lambda: "The same text is translated differently elsewhere",
            "not_translated": lambda: "Not translated",
            "partly_translated": lambda: "Left untranslated: " + ", ".join(map(str, d["left"])),  # type: ignore[call-overload]
            "possible_omission": lambda: "Shorter than expected: part of the text may be missing",
            "foreign_script": lambda: "Contains characters from another language",
            "added_text": lambda: "Has extra lines: the model may have added text",
            "not_written": lambda: "Missing from the written file",
            "original_left": lambda: "The original text is still visible on the page",
            "token_changed": lambda: f"Identifier changed: {d['from']} → {d['to']}",
            "token_missing": lambda: f"Identifier missing: {d['missing']}",
            "token_added": lambda: "Not in the original: " + ", ".join(map(str, d["added"])),  # type: ignore[call-overload]
            "number_changed": lambda: "Number or unit missing or changed: " + ", ".join(map(str, d["missing"])),  # type: ignore[call-overload]
            "overflow": lambda: "Text may not fit its box",
            "font_reduced": lambda: "Font made smaller to fit",
            "box_grows": lambda: "Text box grows with the longer text: check it does not cover other content",
            "overflow_inherited": lambda: "Text runs past its box, as it did in the original",
            "extra_lines": lambda: "Title wraps onto more lines than the original",
            "formatting_simplified": lambda: "Mixed formatting (e.g. bold words) simplified to one style",
            "missing_glyphs": lambda: f"Characters no installed font can show: {d.get('characters', '')}",
            "substitute_font": lambda: "Some characters are shown in a substitute font",
            "font_not_installed": lambda: f"Font not installed on this PC: {d.get('font', '')}",
        }
        try:
            return texts[self.code]() if self.code in texts else self.message
        except KeyError:
            return self.message


@dataclass
class QcReport:
    findings: list[Finding] = field(default_factory=list)
    checked: dict[str, int] = field(default_factory=dict)   # what was checked, e.g. {"paragraphs": 63}

    def sorted(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (_RANK[f.severity], list(CATEGORIES).index(f.category),
                                                    f.pages[:1] or [0]))

    def by_segment(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = defaultdict(list)
        for f in self.findings:
            for sid in f.segments:
                out[sid].append(f)
        return out

    def flagged_segments(self) -> set[str]:
        return {sid for f in self.findings if f.severity != Severity.INFO for sid in f.segments}

    def summary(self) -> dict[str, dict[str, object]]:
        out: dict[str, dict[str, object]] = {}
        for key, label in CATEGORIES.items():
            mine = [f for f in self.findings if f.category == key]
            out[key] = {"label": label,
                        "errors": sum(f.severity == Severity.ERROR for f in mine),
                        "warnings": sum(f.severity == Severity.WARNING for f in mine),
                        "info": sum(f.severity == Severity.INFO for f in mine)}
        return out

    def public(self) -> dict[str, object]:
        """For .report.json: counts and messages, no document text."""
        return {"summary": self.summary(), "checked": self.checked,
                "findings": [f.public() for f in self.sorted()]}
