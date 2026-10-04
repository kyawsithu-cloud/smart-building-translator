from __future__ import annotations

import argparse
from pathlib import Path

from sbt import formats, langdetect, languages
from sbt.app import jobs
from sbt.domain.models import DocumentError
from sbt.engines.profiles import PROFILES
from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("translate", help="translate a .pptx or .pdf file")
    p.add_argument("input", type=Path)
    p.add_argument("--src", default="auto", help="source language (en, ja, zh, ko, my, th, de, fr, es) or auto")
    p.add_argument("--tgt", default="auto", help="target language, or auto (your usual target language from the "
                                                 "app's settings; otherwise en→ja, ja→en, others→en)")
    p.add_argument("--out", type=Path, help="output file (default: <name>_<LANG>.pptx next to the input)")
    p.add_argument("--model", default=cfg.model, choices=sorted(PROFILES))
    p.add_argument("--repair-model", default=cfg.repair_model,
                   help="second model for segments that are still flagged, e.g. qwen3-8b")
    p.add_argument("--glossary", default=cfg.glossary, help="glossary name (see `glossary names`)")
    p.add_argument("--doc-terms", default=cfg.doc_terms, choices=["off", "vote", "hint", "enforce"])
    p.add_argument("--protect", default=cfg.protect, choices=["verify", "mask"])
    p.add_argument("--no-memory", action="store_true", help="don't reuse or store translations for this job")
    p.add_argument("--cpu", action="store_true", help="CPU only (when a game or other app is using the GPU)")
    p.add_argument("--no-ocr", action="store_true", help="don't read scanned pages / text in pictures")
    p.set_defaults(func=run)


def run(args: argparse.Namespace, cfg: Settings) -> int:
    src_path: Path = args.input.resolve()
    if not src_path.exists():
        print(f"[X] File not found: {src_path}")
        return 1
    try:
        return _run(args, cfg, src_path)
    except DocumentError as e:
        print(f"[X] {e}")
        return 1


def _run(args: argparse.Namespace, cfg: Settings, src_path: Path) -> int:
    formats.check_supported(src_path)
    src = args.src
    if src == "auto":
        parsed = formats.parser_for(src_path, None, not args.no_ocr).parse(src_path)
        text = "\n".join(s.plain_source for s in parsed.segments)
        if not text.strip():
            print("[X] No text found in the document (for scanned PDFs, OCR may be switched off or unavailable "
                  "for this language). Use --src to set the language.")
            return 1
        found = langdetect.detect(text)
        src = found.language
        print(f"Detected source language: {languages.get(src).name} (confidence {found.confidence:.0%})")
    tgt = langdetect.default_target(src, cfg.target_lang) if args.tgt == "auto" else args.tgt
    languages.get(src), languages.get(tgt)
    if src == tgt:
        print(f"[X] Source and target are both {languages.get(src).name}. Use --tgt to choose a target.")
        return 1
    out = (args.out or src_path.with_name(f"{src_path.stem}_{tgt.upper()}{src_path.suffix}")).resolve()

    cfg.glossary = args.glossary
    if args.cpu:
        cfg.gpu = "cpu"
    spec = jobs.JobSpec(src_path, out, src, tgt, args.model, args.repair_model, args.protect, args.doc_terms,
                        cfg.min_font_scale, ocr=not args.no_ocr)
    print(f"OFFLINE MODE — {languages.get(src).name} → {languages.get(tgt).name} with {args.model} on this "
          "computer. Nothing is sent to the network.")
    try:
        report = jobs.run(spec, cfg, use_memory=not args.no_memory).report
    except FileNotFoundError as e:
        print(f"[X] {e}\n    Copy the runtime folder from a working PC, or see MODEL_SETUP.md.")
        return 1
    except PermissionError:
        print(f"[X] Cannot write {out.name}. Is it open in PowerPoint? Close it and try again.")
        return 1
    except (RuntimeError, TimeoutError) as e:
        print(f"[X] The translation engine could not start: {e}\n    Try again with --cpu.")
        return 1
    _summary(report)
    return 0


def _summary(r: dict[str, object]) -> None:
    quality = r.get("quality") or {}
    assert isinstance(quality, dict)
    summary: dict[str, dict[str, object]] = quality.get("summary") or {}
    serious = [f for f in quality.get("findings") or [] if f["severity"] != "info"]
    head = "Translation completed" + (" with warnings." if serious else ".")
    print(f"\n{head}\n  Output:      {r['output']}\n  Translated:  {r['translated_pct']}% of text "
          f"({r['translated_segments']}/{r['segments']} paragraphs), translation time {r['seconds']} s")
    print(f"  Checks:      identifiers {_pct(r['protected_token_integrity_pct'])}, glossary "
          f"{_pct(r['glossary_adherence_pct'])}, formatting {_pct(r['tag_integrity_pct'])}")
    if r.get("doc_terms") or r.get("doc_terms_unresolved"):
        print(f"  Term sheet:  {r['doc_terms']} recurring terms, used consistently in "
              f"{r['doc_term_consistency_pct']}% of places; {r.get('harmonised', 0)} paragraph(s) aligned")
        if r.get("doc_terms_unresolved"):
            print(f"  ! {r['doc_terms_unresolved']} recurring term(s) translated inconsistently — choose a "
                  "translation in .terms.csv, then `python -m sbt glossary import <file>.terms.csv`")
    counts = r.get("status_counts") or {}
    if isinstance(counts, dict) and counts.get("memory"):
        print(f"  Memory:      {counts['memory']} paragraph(s) reused from earlier translations")
    if r.get("repair_tried"):
        print(f"  Repair:      {r['repair_model']} tried {r['repair_tried']} flagged paragraph(s), improved "
              f"{r.get('repaired', 0)}")
    elif r.get("repair_note"):
        print(f"  Repair:      skipped ({r['repair_note']})")
    print("  Quality checks:")
    for row in summary.values():
        errors, warnings = row["errors"], row["warnings"]
        status = "OK" if not errors and not warnings else ", ".join(
            x for x in (f"{errors} error(s)" if errors else "", f"{warnings} to check" if warnings else "") if x)
        print(f"    {row['label']:<32} {status}")
    for f in serious[:15]:
        print(f"    ! {f['message']}")
    if len(serious) > 15:
        print(f"    … {len(serious) - 15} more — see the 'checks' column of the review sheet")
    for notice in r.get("notices") or []:      # type: ignore[union-attr]
        if str(notice).startswith("WARNING"):
            print(f"  ! {str(notice)[9:]}")
    if r.get("ocr_segments"):
        print(f"  OCR:         {r['ocr_segments']} paragraph(s) read from scanned pages — check them in the review "
              "sheet (OCR can misread characters)")


def _pct(v: object) -> str:
    return "n/a" if v is None else f"{v}%"

