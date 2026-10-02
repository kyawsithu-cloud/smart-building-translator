from __future__ import annotations

import zipfile
from pathlib import Path

import pymupdf
import pytest

from sbt import formats
from sbt.domain.models import DocumentError, SegmentKind
from sbt.ocr import ja_fix
from sbt.parsers.pdf_parser import _BULLET, PdfParser
from sbt.parsers.pptx_parser import PptxParser
from sbt.renderers.pdf_renderer import PdfRenderer, available_rect
from sbt.renderers.pptx_renderer import PptxRenderer

TESTSET = Path(__file__).resolve().parents[2] / "eval" / "testset"


def _need(name: str) -> Path:
    path = TESTSET / name
    if not path.exists():
        pytest.skip(f"{name} missing: run scripts/make_pdf_testset.py / make_rich_deck.py")
    return path


# --- file handling --------------------------------------------------------------------------------------------
def test_unsupported_and_broken_files_give_clear_errors(tmp_path: Path) -> None:
    with pytest.raises(DocumentError, match="Save it as .pptx"):
        formats.check_supported(Path("old.ppt"))
    with pytest.raises(DocumentError, match="password-protected"):
        PdfParser("en").parse(_need("protected.pdf"))
    damaged = PdfParser("en", ocr=False).parse(_need("corrupt.pdf"))     # repaired by MuPDF, but never silently
    assert any(n.startswith("WARNING") and "damaged" in n for n in damaged.notices)
    fake = tmp_path / "fake.pptx"
    fake.write_bytes(b"not a zip")
    with pytest.raises(DocumentError, match="could not be opened"):
        PptxParser().parse(fake)


# --- PDF parsing ---------------------------------------------------------------------------------------------
def test_pdf_paragraphs_tables_bullets_and_identifiers() -> None:
    model = PdfParser("en", ocr=False).parse(_need("spec_en.pdf"))
    texts = [s.source for s in model.segments]
    cells = [s for s in model.segments if s.kind == SegmentKind.TABLE_CELL]
    assert {"BMS server", "192.168.1.100", "mqtt.example.com:8883"} <= {s.source for s in cells}
    assert any("FX-PCG2611-0" in t for t in texts)                       # soft hyphens normalised
    bullets = [s for s in model.segments if s.geometry["prefix"].strip() == "•"]
    assert len(bullets) == 4 and not any(s.source.startswith("•") for s in bullets)
    headings = [s.source for s in model.segments if s.kind == SegmentKind.TITLE]
    assert "Scope" in headings and "BMS Integration Specification" in headings


def test_exported_slides_rebuild_split_sentences() -> None:
    model = PdfParser("en", ocr=False).parse(_need("slides_en.pdf"))
    texts = [s.plain_source for s in model.segments]
    assert "Air Handling Unit (AHU) and Fan Coil Unit (FCU) control" in texts       # was split over 2 blocks
    assert {"Edge device", "Gateway", "Cloud platform", "Dashboard"} <= set(texts)  # side-by-side labels


def test_scanned_pdf_is_read_by_ocr() -> None:
    model = PdfParser("en").parse(_need("spec_en_scanned.pdf"))
    texts = " ".join(s.plain_source for s in model.segments)
    assert "BMS Integration Specification" in texts and "192.168.1.100" in texts
    assert all(s.ocr_confidence is not None for s in model.segments)
    assert any("OCR" in n for n in model.notices)


@pytest.mark.parametrize("text,prefix", [("•可変", "•"), ("2.システム", "2."),
                                         ("1. Scope", "1. "), ("2.1 Overview", None), ("-5 °C", None)])
def test_list_markers(text: str, prefix: str | None) -> None:
    m = _BULLET.match(text)
    assert (m.group(0) if m else None) == prefix


# --- PDF rendering -------------------------------------------------------------------------------------------
def test_pdf_render_replaces_text_and_keeps_identifiers(tmp_path: Path) -> None:
    src = _need("spec_en.pdf")
    model = PdfParser("en", ocr=False).parse(src)
    for s in model.segments:
        if s.source == "Scope":
            s.translation = "適用範囲"      # 適用範囲
    out = tmp_path / "out.pdf"
    PdfRenderer("en", "ja").render(model, out)
    text = pymupdf.open(out)[0].get_text()
    assert "適用範囲" in text and "Scope" not in text
    assert "192.168.1.100" in text                                     # untouched text is still there
    with pytest.raises(ValueError):
        PdfRenderer("en", "ja").render(model, src)                       # never overwrite the original


def test_available_rect_grows_into_free_space_only() -> None:
    page = pymupdf.Rect(0, 0, 595, 842)
    text = pymupdf.Rect(70, 100, 200, 112)
    grown = available_rect(text, page, others=[], boxes=[], column_right=520)
    assert grown.x1 == 520 and grown.y1 > text.y1
    below = pymupdf.Rect(70, 115, 400, 127)
    assert available_rect(text, page, [below], [], 520).y1 <= below.y0
    box = pymupdf.Rect(60, 90, 250, 130)                                # text inside a drawn shape
    inside = available_rect(text, page, [], [box], 520)
    assert inside.x1 <= box.x1 and inside.y1 <= box.y1


# --- OCR clean-up --------------------------------------------------------------------------------------------
def test_japanese_ocr_fixes() -> None:
    assert ja_fix.fix("設定值") == "設定値"           # 設定值 → 設定値
    assert ja_fix.fix("冷冻机") == "冷凍機"           # 冷冻机 → 冷凍機
    assert ja_fix.fix("工スカレー") == "エスカレー"   # 工スカレー
    assert ja_fix.fix("工場") == "工場"                       # 工場 stays
    assert ja_fix.fix("机の上") == "机の上"           # 机の上 stays


# --- PPTX charts, SmartArt, pictures -------------------------------------------------------------------------
def test_chart_labels_are_found_and_written(tmp_path: Path) -> None:
    src = _need("rich_en.pptx")
    model = PptxParser(ocr_images=False).parse(src)
    chart = [s for s in model.segments if s.kind == SegmentKind.CHART]
    assert {"Energy Consumption by System", "System", "MWh per year", "Chiller", "Target (MWh)"} <= \
        {s.source for s in chart}
    for s in chart:
        s.translation = s.source.upper()
    out = tmp_path / "out.pptx"
    PptxRenderer("en", "en").render(model, out)
    again = {s.source for s in PptxParser(ocr_images=False).parse(out).segments if s.kind == SegmentKind.CHART}
    assert "CHILLER" in again and "ENERGY CONSUMPTION BY SYSTEM" in again


def test_smartart_data_and_cached_drawing_are_both_updated(tmp_path: Path) -> None:
    src = _need("external/smartart-simple.pptx")
    model = PptxParser(ocr_images=False).parse(src)
    nodes = [s for s in model.segments if "/smartart/" in s.id]
    assert [s.source for s in nodes] == ["abc", "def", "ghi"]
    for s in nodes:
        s.translation = s.source.upper() + "-T"
    out = tmp_path / "out.pptx"
    PptxRenderer("en", "en").render(model, out)
    with zipfile.ZipFile(out) as z:
        data = z.read("ppt/diagrams/data1.xml").decode()
        drawing = next(z.read(n).decode() for n in z.namelist() if n.startswith("ppt/diagrams/drawing"))
    assert "ABC-T" in data and "ABC-T" in drawing and ">abc<" not in drawing


def test_picture_with_text_is_reported_but_plain_picture_is_not() -> None:
    model = PptxParser(ocr_images=True, source_lang="en").parse(_need("rich_en.pptx"))
    assert model.untranslatable.count("slide 2: picture contains text (not translated)") == 1


def test_output_polish_for_cjk_spacing_and_list_markers() -> None:
    from sbt.protection import tokens as tok
    from sbt.renderers.pdf_renderer import target_prefix
    assert tok.tidy("x", "\u7ba1\u7406\u30b7\u30b9\u30c6\u30e0 \u306f \u6d88\u8cbb\u91cf \u306e", "ja") == \
        "\u7ba1\u7406\u30b7\u30b9\u30c6\u30e0\u306f\u6d88\u8cbb\u91cf\u306e"
    assert tok.tidy("x", "BMS \u306f", "ja") == "BMS \u306f"            # Latin–Japanese spacing is left alone
    assert target_prefix("\u30fb ", True) == "\u2022 " and target_prefix("2.", True) == "2. "
    assert target_prefix("2.", False) == "2."
