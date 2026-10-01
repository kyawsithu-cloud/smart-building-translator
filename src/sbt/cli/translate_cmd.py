from __future__ import annotations

import argparse
from pathlib import Path

from sbt import langdetect, languages
from sbt.app import jobs
from sbt.engines.profiles import PROFILES
from sbt.parsers.pptx_parser import PptxParser
from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("translate", help="translate a .pptx file")
    p.add_argument("input", type=Path)
    p.add_argument("--src", default="auto", help="source language (en, ja, zh, ko, my, th, de, fr, es) or auto")
    p.add_argument("--tgt", default="auto", help="target language, or auto (en→ja, ja→en, others→en)")
    p.add_argument("--out", type=Path, help="output file (default: <name>_<LANG>.pptx next to the input)")
    p.add_argument("--model", default=cfg.model, choices=sorted(PROFILES))
    p.add_argument("--repair-model", default=cfg.repair_model,
                   help="second model for segments that are still flagged, e.g. qwen3-8b")
    p.add_argument("--glossary", default=cfg.glossary, help="glossary name (see `glossary names`)")
    p.add_argument("--doc-terms", default=cfg.doc_terms, choices=["off", "vote", "hint", "enforce"])
    p.add_argument("--protect", default=cfg.protect, choices=["verify", "mask"])
    p.add_argument("--no-memory", action="store_true", help="don't reuse or store translations for this job")
    p.add_argument("--cpu", action="store_true", help="CPU only (when a game or other app is using the GPU)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace, cfg: Settings) -> int:
    src_path: Path = args.input.resolve()
    if not src_path.exists():
        print(f"[X] File not found: {src_path}")
        return 1
    if src_path.suffix.lower() != ".pptx":
        print("[X] Only .pptx files are supported in this version. Save .ppt files as .pptx first; "
              "PDF support comes in Phase 3.")
        return 1
    src = args.src
    if src == "auto":
        text = "\n".join(s.plain_source for s in PptxParser().parse(src_path).segments)
        found = langdetect.detect(text)
        src = found.language
        print(f"Detected source language: {languages.get(src).name} (confidence {found.confidence:.0%})")
    tgt = langdetect.default_target(src) if args.tgt == "auto" else args.tgt
    languages.get(src), languages.get(tgt)
    if src == tgt:
        print(f"[X] Source and target are both {languages.get(src).name}. Use --tgt to choose a target.")
        return 1
    out = (args.out or src_path.with_name(f"{src_path.stem}_{tgt.upper()}{src_path.suffix}")).resolve()

    cfg.glossary = args.glossary
    if args.cpu:
        cfg.gpu = "cpu"
    spec = jobs.JobSpec(src_path, out, src, tgt, args.model, args.repair_model, args.protect, args.doc_terms,
                        cfg.min_font_scale)
    print(f"OFFLINE MODE — {languages.get(src).name} → {languages.get(tgt).name} with {args.model} on this "
          "computer. Nothing is sent to the network.")
    try:
        report = jobs.run(spec, cfg, use_memory=not args.no_memory)
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
    issues = r["issues"]
    assert isinstance(issues, list)
    serious = [i for i in issues if i["severity"] != "info"]
    head = "Translation completed" + (" with warnings." if serious else ".")
    print(f"\n{head}\n  Output:      {r['output']}\n  Translated:  {r['translated_pct']}% of text "
          f"({r['translated_segments']}/{r['segments']} paragraphs), translation time {r['seconds']} s")
    print(f"  Checks:      identifiers {r['protected_token_integrity_pct']}%, glossary "
          f"{r['glossary_adherence_pct']}%, formatting {_pct(r['tag_integrity_pct'])}")
    if r.get("doc_terms") or r.get("doc_terms_unresolved"):
        print(f"  Term sheet:  {r['doc_terms']} recurring terms, used consistently in "
              f"{r['doc_term_consistency_pct']}% of places; {r.get('harmonised', 0)} paragraph(s) aligned")
        if r.get("doc_terms_unresolved"):
            print(f"  ! {r['doc_terms_unresolved']} recurring term(s) translated inconsistently — choose a "
                  "translation in .terms.csv, then `python -m sbt glossary import <file>.terms.csv`")
    counts = r.get("status_counts") or {}
    if isinstance(counts, dict) and counts.get("memory"):
        print(f"  Memory:      {counts['memory']} paragraph(s) reused from earlier translations")
    if r.get("repaired"):
        print(f"  Repair:      {r['repaired']} paragraph(s) improved by {r['repair_model']}")
    elif r.get("repair_note"):
        print(f"  Repair:      skipped ({r['repair_note']})")
    by_code: dict[str, int] = {}
    for i in issues:
        by_code[i["code"]] = by_code.get(i["code"], 0) + 1
    for code, n in sorted(by_code.items()):
        print(f"  ! {n} × {_EXPLAIN.get(code, code)}")
    untranslatable = r.get("untranslatable") or []
    if untranslatable:
        print(f"  ! {len(untranslatable)} item(s) not translatable (pictures, charts, fields) — see report")


def _pct(v: object) -> str:
    return "n/a" if v is None else f"{v}%"


_EXPLAIN = {
    "overflow": "text box may overflow even after shrinking the font",
    "font_reduced": "text box font reduced to fit (informational)",
    "term_missing": "required glossary term not used — check in the review sheet",
    "token_missing": "identifier/number changed — check in the review sheet",
    "untranslated": "paragraph left untranslated",
    "empty": "paragraph could not be translated",
    "tags": "formatting could not be mapped; paragraph uses one style",
    "foreign_script": "characters from another language appeared",
    "number_mismatch": "a number may have changed — check in the review sheet",
    "length_suspicious": "translation unusually short/long (possible omission)",
    "term_inconsistent": "glossary term translated inconsistently",
    "placeholders": "protected placeholder lost",
    "parentheses_lost": "brackets around an acronym were dropped",
}
