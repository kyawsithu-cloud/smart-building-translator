from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import numpy as np
from pptx import Presentation
from pptx.exc import PackageNotFoundError

from sbt.domain.models import DocumentError, DocumentModel, Segment
from sbt.parsers.pptx_walk import (ImageRef, Notice, ParagraphRef, SmartArtRef, TextNodeRef, encode_paragraph,
                                   flush_parts, walk)
from sbt.pipeline.tags import tag_ids

MIN_PICTURE_PIXELS = 20_000      # smaller pictures (icons, logos) are not checked for text


def open_presentation(path: Path):  # type: ignore[no-untyped-def]
    try:
        return Presentation(str(path))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as e:
        raise DocumentError("The PowerPoint file could not be opened; it may be damaged, password-protected or "
                            f"not a real .pptx ({type(e).__name__}).") from None


class PptxParser:
    file_types = frozenset({"pptx"})

    def __init__(self, ocr_images: bool = True, source_lang: str | None = None) -> None:
        self.ocr_images = ocr_images
        self.source_lang = source_lang
        self._seen: dict[str, bool] = {}

    def parse(self, path: Path) -> DocumentModel:
        prs = open_presentation(path)
        model = DocumentModel(str(path), "pptx", len(prs.slides))
        try:
            for item in walk(prs):
                if isinstance(item, str):
                    model.untranslatable.append(item)
                elif isinstance(item, Notice):
                    if item.text not in model.notices:
                        model.notices.append(item.text)
                elif isinstance(item, ImageRef):
                    if self.ocr_images and self._picture_has_text(item.blob):
                        model.untranslatable.append(f"slide {item.slide_no}: picture contains text (not translated)")
                elif isinstance(item, SmartArtRef):
                    continue
                elif isinstance(item, TextNodeRef):
                    text = (item.element.text or "").strip()
                    if text:
                        model.segments.append(Segment(item.segment_id, item.kind, item.slide_no, item.shape_key,
                                                      text))
                elif isinstance(item, ParagraphRef):
                    enc = encode_paragraph(item.element)
                    if not enc.text.strip():
                        continue
                    if enc.has_field:
                        model.untranslatable.append(f"slide {item.slide_no}: paragraph with a field (kept as-is)")
                        continue
                    model.segments.append(Segment(
                        id=item.segment_id, kind=item.kind, container=item.slide_no, shape_key=item.shape_key,
                        source=enc.text, tag_ids=frozenset(tag_ids(enc.text)),
                    ))
        finally:
            flush_parts(prs)           # releases the parsed SmartArt parts (nothing is written to the file)
        return model

    def _picture_has_text(self, blob: bytes) -> bool:
        digest = hashlib.sha1(blob).hexdigest()
        if digest in self._seen:
            return self._seen[digest]
        found = False
        try:
            from PIL import Image

            from sbt.ocr import engine
            with Image.open(io.BytesIO(blob)) as img:
                if img.width * img.height >= MIN_PICTURE_PIXELS:
                    found = engine.image_has_text(np.asarray(img.convert("RGB")), self.source_lang or "en")
        except (OSError, ValueError):          # EMF/WMF and other formats Pillow cannot read
            found = False
        self._seen[digest] = found
        return found
