"""Entry point of SmartBuildingTranslator.exe (the desktop app, no console window)."""
import argparse
import sys
from pathlib import Path

from sbt.ui.app import main

parser = argparse.ArgumentParser(prog="SmartBuildingTranslator")
parser.add_argument("--debug", action="store_true", help="browser developer tools")
parser.add_argument("--selftest", type=Path, help="check the build, write the result to this file, close")
parser.add_argument("--selftest-document", type=Path, help="with --selftest: also translate this document")
args, _ = parser.parse_known_args()      # a windowed program cannot show argparse errors: ignore unknown ones
sys.exit(main(debug=args.debug, selftest=args.selftest, selftest_document=args.selftest_document))
