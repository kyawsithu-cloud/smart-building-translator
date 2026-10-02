"""OCR accuracy on the scanned test PDFs: character error rate (CER) against the text of the original PDF.

Line-matched CER: every reference line is paired with the OCR line closest to it; CER = summed edit distance /
reference characters (whitespace removed). This measures recognition, not reading order (a table read
column-by-column instead of row-by-row would otherwise count as errors). The page-level CER, which does include
order, is shown for comparison. Reported before and after the Japanese OCR clean-up (ocr/ja_fix.py).

    py scripts/ocr_eval.py
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata

import numpy as np
import pymupdf
from rapidfuzz.distance import Levenshtein

from sbt.ocr import engine
from sbt.privacy import network_guard
from sbt.settings import PROJECT_ROOT

TESTSET = PROJECT_ROOT / "eval" / "testset"
PAIRS = [("spec_en_scanned.pdf", "spec_en.pdf", "en"), ("spec_ja_scanned.pdf", "spec_ja.pdf", "ja")]


def _norm(text: str) -> str:
    text = text.replace("\u00ad", "-").replace("\u00a0", " ")
    return re.sub(r"\s+", "", text)


_SAME = str.maketrans({"\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2010": "-", "\u30fb": "\u2022",
                       "\u301c": "~"})


def _notation(text: str) -> str:
    """Ignore notation that means the same to a reader and to the translator: full-/half-width forms (（）/(),
    ％/%, ～/~), dash and bullet variants."""
    return unicodedata.normalize("NFKC", _norm(text)).translate(_SAME)


def line_cer(ocr_lines: list[str], ref_lines: list[str], norm=_norm) -> float:  # type: ignore[no-untyped-def]
    ocr = [norm(x) for x in ocr_lines if norm(x)]
    errors = total = 0
    for ref in (norm(x) for x in ref_lines):
        if not ref:
            continue
        total += len(ref)
        errors += min((Levenshtein.distance(ref, o) for o in ocr), default=len(ref))
    return errors / max(1, total)


def main() -> None:
    network_guard.install()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print("| file | page | ref chars | single pass | pipeline (re-read + clean-up) | pipeline, notation ignored "
          "| page CER incl. order | seconds |")
    print("|---|---|---|---|---|---|---|---|")
    for scanned, original, lang in PAIRS:
        with pymupdf.open(TESTSET / scanned) as scan, pymupdf.open(TESTSET / original) as ref:
            for pno, (page, ref_page) in enumerate(zip(scan, ref, strict=True), start=1):
                pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
                img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                t0 = time.perf_counter()
                fixed_lines = [ln.text for ln in engine.read(img, lang)]   # pipeline OCR incl. re-read + clean-up
                seconds = time.perf_counter() - t0
                raw = engine._engine(lang)(img, use_det=True, use_cls=False, use_rec=True)   # single pass
                ocr_lines = list(raw.txts or ())
                fixed = "".join(fixed_lines)
                reference = _norm(ref_page.get_text())
                ref_lines = ref_page.get_text().splitlines()
                page_cer = Levenshtein.distance(_norm(fixed), reference) / max(1, len(reference))
                print(f"| {scanned} | {pno} | {len(reference)} | {line_cer(ocr_lines, ref_lines):.2%} | "
                      f"{line_cer(fixed_lines, ref_lines):.2%} | {line_cer(fixed_lines, ref_lines, _notation):.2%} | "
                      f"{page_cer:.2%} | {seconds:.1f} |")


if __name__ == "__main__":
    main()
