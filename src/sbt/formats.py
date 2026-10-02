"""Which parser and renderer handle which file type."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sbt.domain.models import DocumentError, DocumentModel, Issue

SUPPORTED = (".pptx", ".pdf")


class Parser(Protocol):
    def parse(self, path: Path) -> DocumentModel: ...


class Renderer(Protocol):
    def render(self, model: DocumentModel, output_path: Path) -> list[Issue]: ...


def check_supported(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED:
        return suffix
    hints = {".ppt": "Save it as .pptx in PowerPoint first.", ".doc": "Word files are not supported yet.",
             ".docx": "Word files are not supported yet.", ".xlsx": "Excel files are not supported yet."}
    raise DocumentError(f"{suffix or 'This file type'} is not supported. Supported: .pptx, .pdf. "
                        + hints.get(suffix, ""))


def parser_for(path: Path, source_lang: str | None = None, ocr: bool = True) -> Parser:
    suffix = check_supported(path)
    if suffix == ".pptx":
        from sbt.parsers.pptx_parser import PptxParser
        return PptxParser(ocr_images=ocr, source_lang=source_lang)
    from sbt.parsers.pdf_parser import PdfParser
    return PdfParser(source_lang=source_lang, ocr=ocr)


def renderer_for(path: Path, source_lang: str, target_lang: str, min_font_scale: float) -> Renderer:
    suffix = check_supported(path)
    if suffix == ".pptx":
        from sbt.renderers.pptx_renderer import PptxRenderer
        return PptxRenderer(source_lang, target_lang, min_font_scale)
    from sbt.renderers.pdf_renderer import PdfRenderer
    return PdfRenderer(source_lang, target_lang, min_font_scale)
