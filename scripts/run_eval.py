"""Phase 1 evaluation: every installed model × every direction on the public test decks.

Writes, per run, the translated deck + report.json + review.csv, and an overall scorecard:
    eval/results/phase1/summary.md

    py scripts/run_eval.py                       # EN↔JA for all models
    py scripts/run_eval.py --extra zh ko th my   # plus EN→other languages for multilingual models
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from sbt.engines.profiles import PROFILES
from sbt.poc.job import JobSpec, run_job
from sbt.poc.server import ROOT, RUNTIME, LlamaServer
from sbt.privacy import network_guard

TESTSET = ROOT / "eval" / "testset"
OUT = ROOT / "eval" / "results" / "phase1"
GLOSSARY = ROOT / "data" / "terminology" / "smart_building_en_ja.csv"
COLUMNS = ["model", "direction", "translated_pct", "protected_token_integrity_pct", "glossary_adherence_pct",
           "tag_integrity_pct", "warnings", "seconds", "tokens_per_second"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="*", default=list(PROFILES))
    p.add_argument("--extra", nargs="*", default=[], help="extra target languages for EN source")
    p.add_argument("--protect", default="verify", choices=["verify", "mask"])
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    network_guard.install()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    rows = []
    for model_id in args.models:
        profile = PROFILES[model_id]
        if not (RUNTIME / "models" / profile.file).exists():
            print(f"skip {model_id}: model file not installed")
            continue
        runs = [("en", "ja", "sample_en.pptx"), ("ja", "en", "sample_ja.pptx")]
        runs += [("en", t, "sample_en.pptx") for t in args.extra if t in profile.languages]
        with LlamaServer(profile) as server:
            for src, tgt, deck in runs:
                out_dir = OUT / model_id
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{Path(deck).stem}_{src}-{tgt}_{args.protect}.pptx"
                print(f"== {model_id} {src}->{tgt}")
                report = run_job(JobSpec(TESTSET / deck, out, src, tgt, GLOSSARY, args.protect), profile,
                                 server.url)
                report["direction"] = f"{src}→{tgt}"
                report["warnings"] = len(report["issues"])  # type: ignore[arg-type]
                rows.append(report)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"summary_{args.protect}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                                                      encoding="utf-8")
    lines = ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]
    lines += ["| " + " | ".join(str(r.get(c, "")) for c in COLUMNS) + " |" for r in rows]
    (OUT / f"summary_{args.protect}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
