"""Kept for existing instructions: same as `python -m sbt download [--only NAME ...]`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sbt.download import main

if __name__ == "__main__":
    sys.exit(main())
