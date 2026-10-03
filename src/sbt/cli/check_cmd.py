from __future__ import annotations

import argparse
from pathlib import Path

from sbt import formats, langdetect, languages
from sbt.app import checks
from sbt.domain.models import DocumentError, Severity
from sbt.quality import CATEGORIES
from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("check", help="quality-check a translation: original file + translated file")
    p.add_argument("original", type=Path)
    p.add_argument("translation", type=Path)
    p.add_argument("--src", default="auto", help="language of the original (default: detected)")
    p.add_argument("--tgt", default="auto", help="language of the translation (default: detected)")
    p.add_argument("--glossary", default=cfg.glossary)
    p.add_argument("--no-model", action="store_true", help="don't use the local model to find recurring terms")
    p.add_argument("--cpu", action="store_true")
    p.set_defaults(func=run)


def _detect(path: Path) -> str:
    parsed = formats.parser_for(path, None, True).parse(path)
    text = "\n".join(s.plain_source for s in parsed.segments)
    if not text.strip():
        raise DocumentError(f"No text found in {path.name}. Use --src/--tgt to set the languages.")
    return langdetect.detect(text).language


def run(args: argparse.Namespace, cfg: Settings) -> int:
    original, translation = args.original.resolve(), args.translation.resolve()
    for p in (original, translation):
        if not p.exists():
            print(f"[X] File not found: {p}")
            return 1
    try:
        src = _detect(original) if args.src == "auto" else args.src
        tgt = _detect(translation) if args.tgt == "auto" else args.tgt
        languages.get(src), languages.get(tgt)
        if src == tgt:
            print(f"[X] Both files are {languages.get(src).name}. Use --src/--tgt.")
            return 1
        print(f"Checking {languages.get(src).name} → {languages.get(tgt).name}")
        cfg.glossary = args.glossary
        if args.cpu:
            cfg.gpu = "cpu"
        job = checks.run_check(checks.CheckSpec(original, translation, src, tgt, cfg.model,
                                                use_model=not args.no_model), cfg)
    except DocumentError as e:
        print(f"[X] {e}")
        return 1
    report = job.report
    print(f"\n{report['matched']} of {report['segments']} paragraphs matched · {report['seconds']} s")
    if job.term_note:
        print(f"[i] {job.term_note}")
    for key, row in job.quality.summary().items():
        errors, warnings = row["errors"], row["warnings"]
        status = "OK" if not errors and not warnings else f"{errors} error(s), {warnings} warning(s)"
        print(f"  {CATEGORIES[key]:<32} {status}")
    shown = [f for f in job.quality.sorted() if f.severity != Severity.INFO][:15]
    for f in shown:
        print(f"    [{f.severity.value}] {f.message}")
    csv_path = job.write_csv(translation.with_suffix(".checks.csv"))
    print(f"\nDetails (with the text concerned): {csv_path}")
    return 0
