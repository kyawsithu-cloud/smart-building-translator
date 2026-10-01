"""Phase 1 CLI.

    python -m sbt.poc translate deck.pptx --src en --tgt ja --model hy-mt2-7b
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sbt.engines.profiles import PROFILES
from sbt.poc.job import JobSpec, run_job
from sbt.poc.server import ROOT, LlamaServer
from sbt.privacy import network_guard


def detect_language(path: Path) -> str:
    """'ja' if Japanese characters make up a meaningful share of the deck's letters, else 'en'."""
    from sbt.languages import LANGUAGES
    from sbt.parsers.pptx_parser import PptxParser
    text = "".join(s.plain_source for s in PptxParser().parse(path).segments)
    ja = len(LANGUAGES["ja"].script.findall(text))
    latin = len(LANGUAGES["en"].script.findall(text))
    return "ja" if ja > 0.2 * (ja + latin) else "en"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sbt.poc")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("translate")
    t.add_argument("input", type=Path)
    t.add_argument("--src", default="auto", help="source language code, or 'auto' (detects English/Japanese)")
    t.add_argument("--tgt", default="auto", help="target language code, or 'auto' (the other of en/ja)")
    t.add_argument("--model", default="hy-mt2-7b", choices=sorted(PROFILES))
    t.add_argument("--protect", default="verify", choices=["verify", "mask"])
    t.add_argument("--glossary", type=Path, default=ROOT / "data" / "terminology" / "smart_building_en_ja.csv")
    t.add_argument("--out", type=Path)
    t.add_argument("--no-cache", action="store_true")
    t.add_argument("--cpu", action="store_true", help="run on the CPU only (slower; use when a game or other app "
                                                         "is using the GPU)")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    network_guard.install()           # offline mode: only 127.0.0.1 connections are possible from here on

    src_path: Path = args.input.resolve()
    if not src_path.exists():
        print(f"File not found: {src_path}")
        return 1
    if src_path.suffix.lower() != ".pptx":
        print("Only .pptx files are supported in this version (PDF comes in Phase 3).")
        return 1
    if args.src == "auto":
        args.src = detect_language(src_path)
        print(f"Detected source language: {args.src}")
    if args.tgt == "auto":
        args.tgt = "en" if args.src == "ja" else "ja"
    out = args.out or src_path.with_name(f"{src_path.stem}_{args.tgt.upper()}{src_path.suffix}")
    profile = PROFILES[args.model]
    spec = JobSpec(src_path, out.resolve(), args.src, args.tgt, args.glossary, args.protect,
                   cache=None if args.no_cache else ROOT / "runtime" / "cache" / f"{profile.id}.json")
    print(f"OFFLINE MODE — model {profile.id} on this computer. Nothing is sent to the network.")
    try:
        with LlamaServer(profile, gpu_layers="0" if args.cpu else None) as server:
            report = run_job(spec, profile, server.url)
    except FileNotFoundError as e:
        print(f"[X] {e}")
        print("    Copy the whole runtime folder (llama + models) from the original PC.")
        return 1
    except PermissionError:
        print(f"[X] Cannot write {out.name}. Is it open in PowerPoint? Close it and try again.")
        return 1
    except (RuntimeError, TimeoutError) as e:
        print(f"[X] The translation engine could not start: {e}")
        print("    Try again with --cpu.")
        return 1
    print(f"Translated: {report['output']}  ({report['translated_pct']}% of text, {report['seconds']} s)")
    for key in ("protected_token_integrity_pct", "glossary_adherence_pct", "tag_integrity_pct"):
        print(f"  {key}: {report[key]}")
    issues = report["issues"]
    if issues:
        print(f"Completed with {len(issues)} warning(s) — see {Path(out).with_suffix('.report.json').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
