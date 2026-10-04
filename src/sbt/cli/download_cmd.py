from __future__ import annotations

import argparse

from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    from sbt.download import ASSETS
    p = sub.add_parser("download", help="download the translation engine / models (pinned, hash-verified)")
    p.add_argument("--only", nargs="*", help="names: " + ", ".join(a.name for a in ASSETS))
    p.set_defaults(func=run)


def run(args: argparse.Namespace, cfg: Settings) -> int:
    from sbt.download import run as download
    return download(args.only)
