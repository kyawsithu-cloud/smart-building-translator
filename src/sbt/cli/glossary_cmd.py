from __future__ import annotations

import argparse
from pathlib import Path

from sbt.settings import Settings
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.terminology.glossary import Term


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    g = sub.add_parser("glossary", help="manage terminology")
    g.add_argument("--name", default=cfg.glossary, help=f"glossary name (default: {cfg.glossary})")
    gs = g.add_subparsers(dest="action", required=True)

    gs.add_parser("names", help="list glossaries").set_defaults(func=names)

    p = gs.add_parser("list", help="list terms")
    p.add_argument("search", nargs="?", default="")
    p.set_defaults(func=list_terms)

    p = gs.add_parser("add", help="add or update a term")
    p.add_argument("source")
    p.add_argument("target", nargs="?", default="", help="omit with --dnt")
    _term_options(p)
    p.add_argument("--src", default="en")
    p.add_argument("--tgt", default="ja")
    p.set_defaults(func=add)

    p = gs.add_parser("edit", help="change fields of a term (by id from `list`)")
    p.add_argument("id", type=int)
    p.add_argument("--source")
    p.add_argument("--target")
    _term_options(p, edit=True)
    p.set_defaults(func=edit)

    p = gs.add_parser("delete", help="delete a term (by id)")
    p.add_argument("id", type=int)
    p.set_defaults(func=delete)

    p = gs.add_parser("import", help="import/update terms from CSV (e.g. a .terms.csv after review)")
    p.add_argument("file", type=Path)
    p.set_defaults(func=import_csv)

    p = gs.add_parser("export", help="export terms to CSV (opens in Excel)")
    p.add_argument("file", type=Path)
    p.set_defaults(func=export_csv)


def _term_options(p: argparse.ArgumentParser, edit: bool = False) -> None:
    p.add_argument("--category", default=None if edit else "")
    p.add_argument("--notes", default=None if edit else "")
    p.add_argument("--priority", choices=["low", "normal", "high"], default=None if edit else "normal")
    p.add_argument("--context", default=None if edit else "",
                   help="comma-separated keywords; the entry is used only when one occurs on the slide")
    p.add_argument("--dnt", action=argparse.BooleanOptionalAction, default=None if edit else False,
                   help="do not translate (keep as-is in every language)")


def _repo(cfg: Settings) -> GlossaryRepo:
    return GlossaryRepo(db.connect(cfg.db_path))


def names(args: argparse.Namespace, cfg: Settings) -> int:
    repo = _repo(cfg)
    repo.ensure(cfg.glossary)
    for n in repo.names():
        print(f"{n}  ({len(repo.terms(n))} terms){'  [default]' if n == cfg.glossary else ''}")
    return 0


def list_terms(args: argparse.Namespace, cfg: Settings) -> int:
    rows = _repo(cfg).terms(args.name, args.search)
    print(f"{'id':>4}  {'pair':<6} {'source':<32} {'target':<24} {'flags':<14} context")
    for st in rows:
        t = st.term
        flags = ",".join(f for f in ("DNT" if t.do_not_translate else "", t.priority if t.priority != "normal"
                                     else "", "draft" if "DRAFT" in t.notes else "") if f)
        print(f"{st.id:>4}  {t.source_lang}>{t.target_lang:<3} {t.source_term[:32]:<32} {t.target_term[:24]:<24} "
              f"{flags:<14} {t.context}")
    print(f"{len(rows)} term(s) in '{args.name}'")
    return 0


def add(args: argparse.Namespace, cfg: Settings) -> int:
    if not args.dnt and not args.target:
        print("[X] Give a target term, or use --dnt for terms that must stay unchanged.")
        return 1
    term = Term(args.source, args.target or args.source, args.src, args.tgt, args.category, args.notes,
                args.dnt, args.priority, args.context)
    tid = _repo(cfg).add(args.name, term)
    print(f"Saved term {tid}: {term.source_term} → {term.target_term}")
    return 0


def edit(args: argparse.Namespace, cfg: Settings) -> int:
    changes = {k: v for k, v in {
        "source_term": args.source, "target_term": args.target, "category": args.category, "notes": args.notes,
        "priority": args.priority, "context": args.context, "do_not_translate": args.dnt}.items() if v is not None}
    if not changes:
        print("[X] Nothing to change. Use e.g. --target, --priority, --context, --dnt/--no-dnt.")
        return 1
    ok = _repo(cfg).update(args.id, **changes)
    print(f"Updated term {args.id}." if ok else f"[X] No term with id {args.id}.")
    return 0 if ok else 1


def delete(args: argparse.Namespace, cfg: Settings) -> int:
    ok = _repo(cfg).delete(args.id)
    print(f"Deleted term {args.id}." if ok else f"[X] No term with id {args.id}.")
    return 0 if ok else 1


def import_csv(args: argparse.Namespace, cfg: Settings) -> int:
    n = _repo(cfg).import_csv(args.name, args.file)
    print(f"Imported {n} term(s) into '{args.name}' (existing entries updated).")
    return 0


def export_csv(args: argparse.Namespace, cfg: Settings) -> int:
    n = _repo(cfg).export_csv(args.name, args.file)
    print(f"Exported {n} term(s) to {args.file}")
    return 0
