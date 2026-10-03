"""Helpers for the quality-control evaluation: rebuild a translated document from an earlier run.

A finished run leaves `<name>.review.csv` (segment id, source, translation) next to its output. Parsing the
original again gives the same segment ids, so the translated document model can be restored without the model.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sbt import formats
from sbt.domain.models import DocumentModel


def load_run(original: Path, review_csv: Path, src: str) -> DocumentModel:
    doc = formats.parser_for(original, src, True).parse(original)
    with review_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = {r["segment"]: r for r in csv.DictReader(f)}
    for s in doc.segments:
        row = rows.get(s.id)
        if row is not None and row["translation"]:
            s.translation = row["translation"]
    return doc
