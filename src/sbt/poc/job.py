"""One translation job: parse → translate → render → report. Used by the CLI and the evaluation runner."""
from __future__ import annotations

import csv
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sbt.engines.llamacpp import LlamaCppEngine
from sbt.engines.profiles import ModelProfile
from sbt.parsers.pptx_parser import PptxParser
from sbt.pipeline.translator import PipelineOptions, TranslationPipeline
from sbt.renderers.pptx_renderer import PptxRenderer
from sbt.terminology.glossary import Glossary

log = logging.getLogger("sbt.job")


@dataclass
class JobSpec:
    input: Path
    output: Path
    source_lang: str
    target_lang: str
    glossary: Path
    protect: str = "verify"
    cache: Path | None = None


def pct(hit: int, total: int) -> float | None:
    return round(100 * hit / total, 1) if total else None


def run_job(spec: JobSpec, profile: ModelProfile, server_url: str) -> dict[str, object]:
    for lang in (spec.source_lang, spec.target_lang):
        if lang not in profile.languages:
            raise ValueError(f"Model {profile.id} does not support language '{lang}'")
    t0 = time.perf_counter()
    model = PptxParser().parse(spec.input)
    log.info("Job started: type=pptx slides=%d segments=%d model=%s %s->%s", model.container_count,
             len(model.segments), profile.id, spec.source_lang, spec.target_lang)

    engine = LlamaCppEngine(profile, server_url)
    pipeline = TranslationPipeline(engine, Glossary.load_csv(spec.glossary),
                                   PipelineOptions(spec.source_lang, spec.target_lang, spec.protect,
                                                   cache_path=spec.cache))
    result = pipeline.run(model, progress=lambda d, n: print(f"  translating {d}/{n}", end="\r", flush=True))
    print()
    render_issues = PptxRenderer(spec.source_lang, spec.target_lang).render(model, spec.output)
    elapsed = time.perf_counter() - t0

    statuses = [o.status for o in result.outcomes.values()]
    tagged = [s for s in model.segments if s.tag_ids]
    report = {
        "file": spec.input.name, "output": spec.output.name, "mode": "offline",
        "model": profile.id, "model_file": profile.file, "licence": profile.licence,
        "source_lang": spec.source_lang, "target_lang": spec.target_lang, "protect": spec.protect,
        "slides": model.container_count, "segments": len(model.segments),
        "status_counts": {k: statuses.count(k) for k in sorted(set(statuses))},
        "translated_pct": pct(sum(s.translation is not None for s in model.segments), len(model.segments)),
        "protected_token_integrity_pct": pct(result.token_hits, result.token_checks),
        "glossary_adherence_pct": pct(result.term_hits, result.term_checks),
        "tag_integrity_pct": pct(sum(not s.formatting_simplified for s in tagged), len(tagged)),
        "seconds": round(elapsed, 1), "llm_calls": engine.stats.calls,
        "completion_tokens": engine.stats.completion_tokens,
        "tokens_per_second": round(engine.stats.completion_tokens / engine.stats.seconds, 1)
        if engine.stats.seconds else None,
        "untranslatable": model.untranslatable,
        "issues": [{"code": i.code, "severity": i.severity.value, "segment": i.segment_id, "message": i.message}
                   for i in result.issues + render_issues],
    }
    spec.output.with_suffix(".report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                                       encoding="utf-8")
    # Side-by-side review sheet (contains document text; written next to the output only).
    with spec.output.with_suffix(".review.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slide", "segment", "kind", "status", "problems", "source", "translation"])
        for s in model.segments:
            o = result.outcomes.get(s.id)
            w.writerow([s.container, s.id, s.kind.value, o.status if o else "", ";".join(o.problems) if o else "",
                        s.source, s.translation or ""])
    log.info("Job finished: segments=%d seconds=%.1f issues=%d", len(model.segments), elapsed,
             len(report["issues"]))  # type: ignore[arg-type]
    return report
