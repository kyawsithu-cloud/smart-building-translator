"""Evaluation on the public test decks: every model × direction (× term-sheet mode), with a scorecard.

Uses the project glossary CSV and no translation memory, so results are reproducible and independent of
the user's own database.

    py scripts/run_eval.py                                  # EN↔JA, all installed models
    py scripts/run_eval.py --models hy-mt2-7b --doc-terms off hint enforce --decks consistency
    py scripts/run_eval.py --extra zh ko th my              # plus EN→other languages
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from sbt.app.jobs import JobSpec, TranslationJob, repair_profile
from sbt.engines.llama_server import LlamaServer, model_path
from sbt.engines.llamacpp import LlamaCppEngine
from sbt.engines.profiles import PROFILES
from sbt.privacy import network_guard
from sbt.settings import PROJECT_ROOT
from sbt.terminology.glossary import Glossary

TESTSET = PROJECT_ROOT / "eval" / "testset"
GLOSSARY = PROJECT_ROOT / "data" / "terminology" / "smart_building_en_ja.csv"
DECKS = {"basic": ("sample_en.pptx", "sample_ja.pptx"),
         "consistency": ("consistency_en.pptx", "consistency_ja.pptx")}
COLUMNS = ["model", "deck", "direction", "doc_terms_mode", "translated_pct", "protected_token_integrity_pct",
           "glossary_adherence_pct", "doc_terms", "doc_term_consistency_pct", "tag_integrity_pct", "warnings",
           "harmonised", "repaired", "seconds", "tokens_per_second"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="*", default=list(PROFILES))
    p.add_argument("--decks", nargs="*", default=list(DECKS))
    p.add_argument("--doc-terms", nargs="*", default=["vote"], choices=["off", "vote", "hint", "enforce"])
    p.add_argument("--extra", nargs="*", default=[], help="extra target languages for EN source")
    p.add_argument("--repair", default="", help="repair model for flagged segments, e.g. qwen3-8b")
    p.add_argument("--out", default="phase2", help="results folder under eval/results")
    args = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    network_guard.install()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    out_root = PROJECT_ROOT / "eval" / "results" / args.out
    glossary = Glossary.load_csv(GLOSSARY)

    rows = []
    for model_id in args.models:
        profile = PROFILES[model_id]
        if not model_path(profile).exists():
            print(f"skip {model_id}: model file not installed")
            continue
        runs = []
        for deck in args.decks:
            en, ja = DECKS[deck]
            runs += [(deck, "en", "ja", en), (deck, "ja", "en", ja)]
            runs += [(deck, "en", t, en) for t in args.extra if t in profile.languages]
        jobs: list[tuple[str, TranslationJob]] = []
        with LlamaServer(profile) as server:
            for deck, src, tgt, file in runs:
                for mode in args.doc_terms:
                    out = out_root / model_id / f"{Path(file).stem}_{src}-{tgt}_{mode}.pptx"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    print(f"== {model_id} {deck} {src}->{tgt} doc_terms={mode}")
                    spec = JobSpec(TESTSET / file, out, src, tgt, model_id, args.repair or "", doc_terms=mode)
                    job = TranslationJob(spec, glossary, memory=None)
                    job.translate(LlamaCppEngine(profile, server.url))
                    jobs.append((deck, job))
        to_repair = [j for _, j in jobs if j.needs_repair() and repair_profile(j.spec)[0] is not None]
        if to_repair:
            rp = PROFILES[args.repair]
            with LlamaServer(rp) as server:          # main model stopped first (VRAM)
                for job in to_repair:
                    print(f"== repair {job.spec.output.name} with {args.repair}")
                    job.repair(LlamaCppEngine(rp, server.url))
        for deck, job in jobs:
            report = job.finish()
            report.update(deck=deck, direction=f"{job.spec.source_lang}→{job.spec.target_lang}",
                          warnings=len(report["issues"]))  # type: ignore[arg-type]
            rows.append(report)

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(str(r.get(c, "")) for c in COLUMNS) + " |" for r in rows]
    (out_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
