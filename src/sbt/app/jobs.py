"""Translation job: parse → (term sheet + translate) → optional repair → render → reports → history.

Progress goes to a Reporter (console for the CLI, shared state for the desktop UI). A Reporter can cancel the
job: its methods raise JobCancelled, which stops the work at the next paragraph/slide.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sbt import formats
from sbt.app import reports
from sbt.engines.base import EngineStats, TranslationEngine
from sbt.engines.llama_server import LlamaServer, model_path
from sbt.engines.llamacpp import LlamaCppEngine
from sbt.engines.profiles import PROFILES, ModelProfile
from sbt.pipeline.translator import PipelineOptions, PipelineResult, TranslationPipeline
from sbt.settings import Settings
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.storage.jobs_repo import JobRepo
from sbt.storage.memory import TranslationMemory
from sbt.terminology.glossary import Glossary

log = logging.getLogger("sbt.job")

# Stages in order, with the label shown to the user.
STAGES = {
    "read": "Reading the document",
    "load": "Loading the translation model",
    "terms": "Finding recurring terms",
    "translate": "Translating",
    "align": "Making terms consistent",
    "repair": "Re-checking flagged paragraphs",
    "write": "Writing the translated document",
}


class JobCancelled(Exception):
    pass


class Reporter:
    """Default reporter: prints to the console (CLI)."""

    def stage(self, key: str) -> None:
        if key in ("translate",):
            return
        print(f"  {STAGES.get(key, key)}...", flush=True)

    def progress(self, done: int, total: int) -> None:
        print(f"  translating {done}/{total}", end="\r" if done < total else "\n", flush=True)


@dataclass
class JobSpec:
    input: Path
    output: Path
    source_lang: str
    target_lang: str
    model: str = "hy-mt2-7b"
    repair_model: str = ""
    protect: str = "verify"
    doc_terms: str = "vote"
    min_font_scale: float = 0.8
    ocr: bool = True                  # scanned PDF pages, text inside pictures


class TranslationJob:
    """One document. Engines are passed in so callers decide how servers are started and shared."""

    def __init__(self, spec: JobSpec, glossary: Glossary, memory: TranslationMemory | None = None,
                 reporter: Reporter | None = None) -> None:
        self.spec = spec
        self.reporter = reporter or Reporter()
        self.profile = _profile(spec.model, spec.source_lang, spec.target_lang)
        t0 = time.perf_counter()
        self.reporter.stage("read")
        self.doc = formats.parser_for(spec.input, spec.source_lang, spec.ocr).parse(spec.input)
        self.active = time.perf_counter() - t0      # seconds spent on this document (excludes model loading)
        self.glossary = glossary
        self.memory = memory
        self.stats = EngineStats()
        self.repaired = 0
        self.repair_note = ""
        self.pipeline: TranslationPipeline | None = None
        self.result: PipelineResult | None = None
        self.report: dict[str, object] = {}
        self.edited: set[str] = set()                # segment ids changed by the user in the review screen
        log.info("Job started: type=%s pages=%d segments=%d model=%s %s->%s", self.doc.file_type,
                 self.doc.container_count, len(self.doc.segments), spec.model, spec.source_lang, spec.target_lang)

    def translate(self, engine: TranslationEngine) -> None:
        t0 = time.perf_counter()
        opts = PipelineOptions(self.spec.source_lang, self.spec.target_lang, self.spec.protect,
                               doc_terms=self.spec.doc_terms)
        self.pipeline = TranslationPipeline(engine, self.glossary, opts, self.memory)
        self.result = self.pipeline.run(self.doc, progress=self.reporter.progress, stage=self.reporter.stage)
        _add_stats(self.stats, engine.stats)
        self.active += time.perf_counter() - t0

    def needs_repair(self) -> bool:
        assert self.pipeline and self.result
        return bool(self.spec.repair_model) and bool(self.pipeline.flagged(self.result))

    def repair(self, engine: TranslationEngine) -> None:
        assert self.pipeline and self.result
        t0 = time.perf_counter()
        self.reporter.stage("repair")
        self.repaired = self.pipeline.repair(self.doc, engine, self.result)
        _add_stats(self.stats, engine.stats)
        self.active += time.perf_counter() - t0
        log.info("Repair: %d segment(s) improved", self.repaired)

    def finish(self) -> dict[str, object]:
        assert self.result is not None
        t0 = time.perf_counter()
        self.reporter.stage("write")
        renderer = formats.renderer_for(self.spec.input, self.spec.source_lang, self.spec.target_lang,
                                        self.spec.min_font_scale)
        render_issues = renderer.render(self.doc, self.spec.output)
        self.active += time.perf_counter() - t0
        meta: dict[str, object] = {
            "file": self.spec.input.name, "output": self.spec.output.name, "mode": "offline",
            "file_type": self.doc.file_type,
            "model": self.profile.id, "model_file": self.profile.file, "licence": self.profile.licence,
            "repair_model": self.spec.repair_model or None, "repaired": self.repaired,
            "repair_note": self.repair_note or None,
            "source_lang": self.spec.source_lang, "target_lang": self.spec.target_lang,
            "protect": self.spec.protect, "doc_terms_mode": self.spec.doc_terms,
            "memory": self.memory is not None and self.memory.enabled,
            "edited_by_user": len(self.edited),
            "seconds": round(self.active, 1), "llm_calls": self.stats.calls,
            "completion_tokens": self.stats.completion_tokens,
            "tokens_per_second": round(self.stats.completion_tokens / self.stats.seconds, 1)
            if self.stats.seconds else None,
        }
        self.report = reports.build(self.doc, self.result, render_issues, meta)
        reports.write_all(self.spec.output, self.doc, self.result, self.report)
        log.info("Job finished: segments=%d seconds=%s issues=%d", len(self.doc.segments), meta["seconds"],
                 len(self.report["issues"]))  # type: ignore[arg-type]
        return self.report

    def apply_edit(self, segment_id: str, translation: str) -> None:
        """A translation corrected by the user (review screen). Stored as human-approved in the memory."""
        seg = next(s for s in self.doc.segments if s.id == segment_id)
        seg.translation = translation
        self.edited.add(segment_id)
        if self.result is not None:
            outcome = self.result.outcomes.get(segment_id)
            if outcome is not None:
                outcome.status, outcome.problems = "edited", []
        if self.memory is not None and translation.strip():
            self.memory.store(self.spec.source_lang, self.spec.target_lang, seg.source, translation,
                              "user", origin="human")
            self.memory.commit()


def run(spec: JobSpec, settings: Settings, use_memory: bool = True,
        reporter: Reporter | None = None) -> TranslationJob:
    """Full job with the user's database: glossary, translation memory and job history.
    Returns the finished job (report in job.report); the document stays in memory for review edits."""
    reporter = reporter or Reporter()
    conn = db.connect(settings.db_path, check_same_thread=False)
    glossary = GlossaryRepo(conn).load(settings.glossary)
    memory = TranslationMemory(conn, enabled=use_memory and settings.use_memory)
    job = TranslationJob(spec, glossary, memory, reporter)
    gpu = "0" if settings.gpu == "cpu" else None
    reporter.stage("load")
    with LlamaServer(job.profile, gpu) as server:
        job.translate(LlamaCppEngine(job.profile, server.url))
    if job.needs_repair():
        rp, why_not = repair_profile(spec)
        if rp is None:
            job.repair_note = why_not
            log.info("Repair skipped: %s", why_not)
        else:
            # The first server is stopped first: an 8 GB GPU cannot hold both models.
            reporter.stage("load")
            with LlamaServer(rp, gpu) as server:
                job.repair(LlamaCppEngine(rp, server.url))
    job.finish()
    JobRepo(conn).record(job.report)
    return job


def _profile(model_id: str, src: str, tgt: str) -> ModelProfile:
    if model_id not in PROFILES:
        raise ValueError(f"Unknown model '{model_id}'. Installed profiles: {', '.join(PROFILES)}")
    profile = PROFILES[model_id]
    for lang in (src, tgt):
        if lang not in profile.languages:
            raise ValueError(f"Model {model_id} does not support language '{lang}'")
    return profile


def repair_profile(spec: JobSpec) -> tuple[ModelProfile | None, str]:
    """The repair model if it can be used for this job; otherwise None and the reason."""
    if spec.repair_model == spec.model:
        return None, "repair model is the same as the main model"
    profile = PROFILES.get(spec.repair_model)
    if profile is None:
        return None, f"unknown repair model '{spec.repair_model}'"
    if not model_path(profile).exists():
        return None, f"{spec.repair_model} is not installed"
    if not {spec.source_lang, spec.target_lang} <= profile.languages:
        return None, f"{spec.repair_model} is not used for this language pair"
    return profile, ""


def _add_stats(total: EngineStats, part: EngineStats) -> None:
    total.calls += part.calls
    total.prompt_tokens += part.prompt_tokens
    total.completion_tokens += part.completion_tokens
    total.seconds += part.seconds
