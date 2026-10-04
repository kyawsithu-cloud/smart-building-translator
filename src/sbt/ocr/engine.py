"""OCR engine: reads text lines with positions from an image. Fully offline.

Models: the multilingual PP-OCRv6 detector + recogniser bundled inside the `rapidocr` package (English,
Japanese, Chinese and Latin-script languages). Korean and Thai need extra models in runtime/ocr (see
MODEL_SETUP.md); there is no Burmese OCR model, so Burmese scans are reported as not translatable.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from sbt.ocr import ja_fix
from sbt.settings import runtime_dir

_EXTRA_REC = {"ko": "korean_PP-OCRv5_rec_mobile.onnx", "th": "th_PP-OCRv5_rec_mobile.onnx"}
_BUNDLED = {"en", "ja", "zh", "de", "fr", "es"}
log = logging.getLogger(__name__)


class OcrUnavailable(Exception):
    pass


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[float, float, float, float]      # x0, y0, x1, y1 in image pixels
    score: float


def available(lang: str) -> bool:
    return lang in _BUNDLED or (lang in _EXTRA_REC and (runtime_dir() / "ocr" / _EXTRA_REC[lang]).exists())


@lru_cache(maxsize=4)
def _engine(lang: str) -> Any:
    from rapidocr import RapidOCR
    params: dict[str, object] = {"Global.log_level": "error"}
    if lang in _EXTRA_REC:
        rec = runtime_dir() / "ocr" / _EXTRA_REC[lang]
        if not rec.exists():
            raise OcrUnavailable(f"OCR model for this language is not installed ({rec.name}); see MODEL_SETUP.md")
        params["Rec.model_path"] = str(rec)
    elif lang not in _BUNDLED:
        raise OcrUnavailable("No offline OCR model exists for this language")
    return RapidOCR(params=params)


REREAD_BELOW = 0.9
_PAD = 8


def _reread(image: np.ndarray, box: tuple[float, float, float, float], lang: str) -> tuple[str, float]:
    """Recognise one line again from a padded crop. The pipeline's own tight crop sometimes garbles long thin
    lines (measured: 'clo s d t s r s ig r in', score 0.65 → correct text, score 1.0)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    h, w = image.shape[:2]
    crop = image[max(0, y0 - _PAD):min(h, y1 + _PAD), max(0, x0 - _PAD):min(w, x1 + _PAD)]
    if crop.size == 0:
        return "", 0.0
    result = _engine(lang)(crop, use_det=False, use_cls=False, use_rec=True)
    if not result.txts:
        return "", 0.0
    return "".join(result.txts), float(min(result.scores))


def read(image: np.ndarray, lang: str, min_score: float = 0.5) -> list[OcrLine]:
    """Text lines in reading order (top to bottom, then left to right)."""
    # Orientation classifier off: rendered pages are upright, and it flipped upright Korean lines into garbage.
    # Flags are explicit because the library keeps the flags of the previous call.
    result = _engine(lang)(image, use_det=True, use_cls=False, use_rec=True)
    if result.txts is None:
        return []
    lines = []
    for text, box, score in zip(result.txts, result.boxes, result.scores, strict=True):
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        if score < REREAD_BELOW:
            text2, score2 = _reread(image, (min(xs), min(ys), max(xs), max(ys)), lang)
            if score2 > score:
                text, score = text2, score2
        if score < min_score or not text.strip():
            continue
        if lang == "ja":
            text = ja_fix.fix(text)
        lines.append(OcrLine(text.strip(), (min(xs), min(ys), max(xs), max(ys)), float(score)))
    return merge_fragments(lines, lang, image)


def _vrule_between(image: np.ndarray | None, left: OcrLine, right: OcrLine) -> bool:
    """True if a drawn vertical line (table column border) separates two pieces on the same line."""
    if image is None:
        return False
    x0, x1 = int(left.box[2]), int(right.box[0])
    y0, y1 = int(max(left.box[1], right.box[1])), int(min(left.box[3], right.box[3]))
    if x1 - x0 < 2 or y1 - y0 < 5:
        return False
    band = image[y0:y1, x0:x1].mean(axis=2) if image.ndim == 3 else image[y0:y1, x0:x1]
    dark = band < float(np.median(band)) - 40
    return bool((dark.mean(axis=0) > 0.8).any())


def merge_fragments(lines: list[OcrLine], lang: str, image: np.ndarray | None = None) -> list[OcrLine]:
    """Join pieces of one text line that the detector split (often around full-width brackets:
    ビル管理システム | (BMS) | の概要): mostly the same height band and a small horizontal gap, and no
    table column border between them (BACnet/IP port | 47808 must stay two cells)."""
    joiner = "" if lang in ("ja", "zh") else " "
    out: list[OcrLine] = []
    for ln in sorted(lines, key=lambda ln: (round(ln.box[1] / 8), ln.box[0])):
        if out:
            prev = out[-1]
            h = min(prev.box[3] - prev.box[1], ln.box[3] - ln.box[1])
            v_overlap = min(prev.box[3], ln.box[3]) - max(prev.box[1], ln.box[1])
            gap = ln.box[0] - prev.box[2]
            if v_overlap > 0.6 * h and -0.2 * h <= gap <= 0.8 * h and not _vrule_between(image, prev, ln):
                out[-1] = OcrLine(prev.text + joiner + ln.text,
                                  (prev.box[0], min(prev.box[1], ln.box[1]), ln.box[2], max(prev.box[3], ln.box[3])),
                                  min(prev.score, ln.score))
                continue
        out.append(ln)
    return out


_BULLET_START = re.compile(r"^\s*([\u2022\u25cf\u25aa\u25e6\u25cb\u25a0\u25a1\u30fb*]|[-\u2013]\s|\(?\d{1,2}[.)](?!\d))")


def _rule_between(image: np.ndarray | None, upper: OcrLine, lower: OcrLine) -> bool:
    """True if a drawn horizontal line (table rule, underline) separates two text lines."""
    if image is None:
        return False
    y0, y1 = int(upper.box[3]), int(lower.box[1])
    x0, x1 = int(max(upper.box[0], lower.box[0])), int(min(upper.box[2], lower.box[2]))
    if y1 - y0 < 2 or x1 - x0 < 10:
        return False
    band = image[y0:y1, x0:x1].mean(axis=2) if image.ndim == 3 else image[y0:y1, x0:x1]
    background = float(np.median(band))
    dark = band < background - 40
    return bool((dark.mean(axis=1) > 0.8).any())


def group_paragraphs(lines: list[OcrLine], image: np.ndarray | None = None) -> list[list[OcrLine]]:
    """Merge lines into paragraphs: just below the previous line (ordinary line spacing), similar height,
    same left edge and horizontal overlap. A bullet or a drawn rule (table row border) always starts a new one."""
    paragraphs: list[list[OcrLine]] = []
    for ln in sorted(lines, key=lambda ln: (ln.box[1], ln.box[0])):
        h = ln.box[3] - ln.box[1]
        target = None
        if not _BULLET_START.match(ln.text):
            for para in reversed(paragraphs[-3:]):
                last = para[-1]
                lh = last.box[3] - last.box[1]
                gap = ln.box[1] - last.box[3]
                overlap = min(ln.box[2], last.box[2]) - max(ln.box[0], last.box[0])
                same_left = abs(ln.box[0] - para[0].box[0]) < 1.5 * lh
                if (0.7 * lh <= h <= 1.4 * lh and -0.3 * lh <= gap <= 0.45 * lh and overlap > 0 and same_left
                        and not _rule_between(image, last, ln)):
                    target = para
                    break
        if target is None:
            paragraphs.append([ln])
        else:
            target.append(ln)
    return paragraphs


def text_colour(image: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> str:
    """Colour of the ink in the given boxes: median of the darkest 15 % of pixels (hex)."""
    pixels = []
    for x0, y0, x1, y1 in boxes:
        region = image[int(y0):int(y1), int(x0):int(x1)].reshape(-1, image.shape[2] if image.ndim == 3 else 1)
        if len(region):
            pixels.append(region)
    if not pixels:
        return "#000000"
    px = np.concatenate(pixels).astype(np.int32)
    lum = px.sum(axis=1) if px.shape[1] > 1 else px[:, 0]
    dark = px[lum <= np.percentile(lum, 15)]
    r, g, b = (np.median(dark, axis=0).astype(int).tolist() + [0, 0, 0])[:3] if px.shape[1] > 1 else [0, 0, 0]
    if max(r, g, b) - min(r, g, b) < 40:           # greyish ink → plain black (scanner noise, anti-aliasing)
        return "#000000"
    return f"#{r:02x}{g:02x}{b:02x}"


def image_has_text(image: np.ndarray, lang: str, min_chars: int = 3) -> bool:
    try:
        return sum(len(ln.text) for ln in read(image, lang, min_score=0.6)) >= min_chars
    except OcrUnavailable:
        return False
