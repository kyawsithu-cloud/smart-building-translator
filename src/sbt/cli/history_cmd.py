from __future__ import annotations

import argparse

from sbt.settings import Settings
from sbt.storage import db
from sbt.storage.jobs_repo import JobRepo
from sbt.storage.memory import TranslationMemory


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    h = sub.add_parser("history", help="recent jobs; `history clear` deletes history and translation memory")
    hs = h.add_subparsers(dest="action")
    c = hs.add_parser("clear", help="delete job history and all stored translations")
    c.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    c.set_defaults(func=clear)
    h.set_defaults(func=show)


def show(args: argparse.Namespace, cfg: Settings) -> int:
    conn = db.connect(cfg.db_path)
    jobs = JobRepo(conn).recent()
    print(f"{'when (UTC)':<20} {'file':<36} {'pair':<6} {'model':<11} {'done':>9} {'warn':>4} {'sec':>6}")
    for j in jobs:
        print(f"{j['finished_at']:<20} {j['file_name'][:36]:<36} {j['source_lang']}>{j['target_lang']:<3} "
              f"{j['model']:<11} {j['translated']:>4}/{j['segments']:<4} {j['warnings']:>4} {j['seconds']:>6.0f}")
    memory = TranslationMemory(conn)
    print(f"\n{len(jobs)} recent job(s). Translation memory: {memory.count()} stored paragraph(s).")
    print(f"Data location: {cfg.db_path.parent}")
    return 0


def clear(args: argparse.Namespace, cfg: Settings) -> int:
    if not args.yes:
        answer = input("Delete all job history and stored translations on this PC? Glossaries are kept. [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1
    conn = db.connect(cfg.db_path)
    jobs = JobRepo(conn).clear()
    paragraphs = TranslationMemory(conn).clear()
    print(f"Deleted {jobs} job record(s) and {paragraphs} stored translation(s).")
    return 0
