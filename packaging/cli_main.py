"""Entry point of sbt.exe (command line: translate, check, glossary, history, doctor, download)."""
import sys

from sbt.cli import main

sys.exit(main())
