from __future__ import annotations

import argparse

from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    p = sub.add_parser("ui", help="open the desktop app")
    p.add_argument("--debug", action="store_true", help="enable the browser developer tools")
    p.set_defaults(func=run)


def run(args: argparse.Namespace, cfg: Settings) -> int:
    from sbt.ui.app import main
    return main(debug=args.debug)
