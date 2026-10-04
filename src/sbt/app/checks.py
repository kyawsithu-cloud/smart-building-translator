"""Check a translation made elsewhere (a colleague, an agency, another tool): original + translated file →
the same quality checks as after our own translations. Nothing is translated or changed.

With the local model installed, recurring terms are found and translated in context first (as during
translation), which lets the terminology check spot terms worded differently; without it, the glossary and
repeated-text checks still run.
"""
from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sbt import quality
from sbt.app.jobs import Reporter
from sbt.engines.base import TranslationEngine
from sbt.engines.llama_server import LlamaServer, engine_path, model_path
from sbt.engines.llamacpp import LlamaCppEngine
from sbt.engines.profiles import PROFILES
from sbt.quality import compare
from sbt.quality import fonts as font_check
from sbt.settings import Settings
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.terminology import term_sheet
from sbt.terminology.glossary import Glossary
from sbt.terminology.term_sheet import TermSheet

log = logging.getLogger("sbt.check")


@dataclass
class CheckSpec:
    input: Path                   # the original document
    output: Path                  # the translation to check
    source_lang: str
    target_lang: str
    model: str = "hy-mt2-7b"
    use_model: bool = True        # find recurring terms with the local model (if installed)
    ocr: bool = True


class CheckJob:
    read_only = True              # Review shows it; editing and rebuilding are for our own translations

    def __init__(self, spec: CheckSpec, glossary: Glossary, reporter: Reporter | None = None) -> None:
        self.spec = spec
        self.glossary = glossary
        self.reporter = reporter or Reporter()
        self.started = time.perf_counter()
        self.reporter.stage("read")
        self.doc = compare.load_pair(spec.input, spec.output, spec.source_lang, spec.ocr)
        self.result = None
        self.edited: set[str] = set()
        self.sheet: TermSheet | None = None
        self.quality = quality.QcReport()
        self.report: dict[str, object] = {}
        self.term_note = ""
        log.info("Check started: type=%s pages=%d segments=%d %s->%s", self.doc.file_type,
                 self.doc.container_count, len(self.doc.segments), spec.source_lang, spec.target_lang)

    def find_terms(self, engine: TranslationEngine) -> None:
        self.reporter.stage("terms")
        self.sheet = term_sheet.build(self.doc.segments, self.spec.source_lang, self.spec.target_lang,
                                      self.glossary, engine, contexts=3)

    def finish(self) -> dict[str, object]:
        self.reporter.stage("check")
        src, tgt = self.spec.source_lang, self.spec.target_lang
        self.quality = quality.check(self.doc, src, tgt, self.glossary, sheet=self.sheet,
                                     render_issues=compare.layout_issues(self.spec.input, self.spec.output, src, tgt))
        if self.spec.output.suffix.lower() == ".pptx":
            self.quality.findings += font_check.check_pptx(
                self.spec.output, {s.id for s in self.doc.segments if s.translation is not None}, tgt)
        paragraphs = [s for s in self.doc.segments]
        self.report = {
            "kind": "check", "file": self.spec.input.name, "translation": self.spec.output.name,
            "file_type": self.doc.file_type, "source_lang": src, "target_lang": tgt,
            "segments": len(paragraphs), "matched": sum(s.translation is not None for s in paragraphs),
            "recurring_terms": len(self.sheet.all_terms) if self.sheet else 0, "term_note": self.term_note,
            "seconds": round(time.perf_counter() - self.started, 1),   # wall time, incl. loading the model
            "untranslatable": self.doc.untranslatable,
            "notices": self.doc.notices, "quality": self.quality.public(),
        }
        log.info("Check finished: segments=%d findings=%d", len(paragraphs), len(self.quality.findings))
        return self.report

    def write_csv(self, path: Path) -> Path:
        """Findings with the paragraphs they concern (contains document text)."""
        by_id = {s.id: s for s in self.doc.segments}
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["severity", "check", "finding", "page/slide", "segment", "source", "translation"])
            for finding in self.quality.sorted():
                label = quality.CATEGORIES[finding.category]
                for sid in finding.segments or [""]:
                    s = by_id.get(sid)
                    w.writerow([finding.severity.value, label, finding.describe(),
                                s.container if s else ",".join(map(str, finding.pages)), sid,
                                s.plain_source if s else "", (s.translation or "") if s else ""])
        return path


def run_check(spec: CheckSpec, settings: Settings, use_memory: bool = False,
              reporter: Reporter | None = None) -> CheckJob:
    reporter = reporter or Reporter()
    conn = db.connect(settings.db_path, check_same_thread=False)
    try:
        glossary = GlossaryRepo(conn).load(settings.glossary)
    finally:
        conn.close()
    job = CheckJob(spec, glossary, reporter)
    profile = PROFILES.get(spec.model)
    usable = (profile is not None and {spec.source_lang, spec.target_lang} <= set(profile.languages)
              and model_path(profile).exists() and engine_path().exists())
    if spec.use_model and usable and profile is not None:
        reporter.stage("load")
        with LlamaServer(profile, "0" if settings.gpu == "cpu" else None) as server:
            job.find_terms(LlamaCppEngine(profile, server.url))
    elif spec.use_model:
        job.term_note = "The translation model is not installed: recurring terms were not compared."
    job.finish()
    return job


def write_findings_csv(doc, report: quality.QcReport, path: Path) -> Path:  # type: ignore[no-untyped-def]
    """Same sheet for our own translations (Review → Export checks)."""
    job = CheckJob.__new__(CheckJob)
    job.doc, job.quality = doc, report
    return CheckJob.write_csv(job, path)
