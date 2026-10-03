"""Command line: python -m sbt <command>.

  translate  translate a .pptx or .pdf (language detected automatically)
  check      quality-check a translation (original + translated file)
  glossary   list / add / edit / delete / import / export terminology
  history    recent jobs; `history clear` deletes job history and translation memory
  doctor     hardware, installed models, recommendation, data location
  ui         open the desktop app
"""
from __future__ import annotations

import argparse
import logging
import sys

from sbt import settings as settings_mod
from sbt.cli import check_cmd, doctor_cmd, glossary_cmd, history_cmd, translate_cmd, ui_cmd
from sbt.privacy import network_guard


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    network_guard.install()           # offline: only 127.0.0.1 connections are possible from here on
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        cfg = settings_mod.load()
    except ValueError as e:
        print(f"[X] Settings: {e}")
        return 1
    parser = argparse.ArgumentParser(prog="python -m sbt", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for module in (translate_cmd, check_cmd, glossary_cmd, history_cmd, doctor_cmd, ui_cmd):
        module.register(sub, cfg)
    args = parser.parse_args(argv)
    try:
        return int(args.func(args, cfg))
    except (ValueError, FileNotFoundError) as e:
        print(f"[X] {e}")
        return 1
