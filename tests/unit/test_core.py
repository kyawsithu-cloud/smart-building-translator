from __future__ import annotations

import socket
from pathlib import Path

import pytest

from sbt.pipeline.tags import is_well_formed, split_spans, strip_tags, tag_ids
from sbt.pipeline.validate import validate
from sbt.protection import tokens as tok
from sbt.terminology.glossary import Glossary, Hint, Term

ROOT = Path(__file__).resolve().parents[2]


def test_tags_roundtrip() -> None:
    text = "The <g1>BMS</g1> monitors <g2>HVAC</g2>."
    assert strip_tags(text) == "The BMS monitors HVAC."
    assert tag_ids(text) == {1, 2}
    assert split_spans(text) == [(None, "The "), (1, "BMS"), (None, " monitors "), (2, "HVAC"), (None, ".")]
    assert is_well_formed(text)
    assert not is_well_formed("<g1>a<g2>b</g2></g1>")
    assert not is_well_formed("<g1>a</g2>")


def test_protected_tokens() -> None:
    text = ("BMS server 192.168.1.100 and https://bms.example.com/dashboard, mail support@example.com, "
            "model FX-PCG2611-0 firmware v3.2.1, CO2 via TCP/IP")
    found = tok.protected_tokens(text, ["BACnet"])
    for expected in ["BMS", "192.168.1.100", "https://bms.example.com/dashboard", "support@example.com",
                     "FX-PCG2611-0", "v3.2.1", "CO2", "TCP/IP", "BACnet"]:
        assert expected in found


def test_mask_unmask() -> None:
    masked, mapping = tok.mask("See https://x.example.com/a and 10.0.0.1:502")
    assert "https" not in masked and len(mapping) == 2
    assert tok.unmask(masked, mapping) == "See https://x.example.com/a and 10.0.0.1:502"


def test_fullwidth_normalisation_keeps_japanese_punctuation() -> None:
    assert tok.normalize_fullwidth("ＢＭＳ（２４時間）") == "BMS（24時間）"


def test_glossary_both_directions_and_longest_match() -> None:
    g = Glossary([Term("Building Management System", "ビル管理システム", "en", "ja"),
                  Term("BACnet", "BACnet", "en", "ja", do_not_translate=True)])
    en = g.match("The building management systems use BACnet.", "en", "ja")
    assert Hint("Building Management System", "ビル管理システム", False) in en
    assert Hint("BACnet", "BACnet", True) in en
    ja = g.match("ビル管理システムはBACnetを使用", "ja", "en")
    assert Hint("ビル管理システム", "Building Management System", False) in ja


def test_seed_glossary_loads() -> None:
    g = Glossary.load_csv(ROOT / "data" / "terminology" / "smart_building_en_ja.csv")
    assert len(g.terms) > 30


def test_validate_detects_problems() -> None:
    hints = (Hint("setpoint", "設定値", False),)
    problems = {p.code for p in validate("Change the <g1>setpoint</g1> on 192.168.1.10",
                                         "<g1>セットポイント</g1>を変更", ["192.168.1.10"], hints, "en", "ja")}
    assert {"token_missing", "term_missing"} <= problems
    ok = validate("Change the <g1>setpoint</g1> on 192.168.1.10",
                  "192.168.1.10の<g1>設定値</g1>を変更", ["192.168.1.10"], hints, "en", "ja")
    assert ok == []
    assert {p.code for p in validate("Alarm", "Alarm", [], (), "en", "ja")} == {"untranslated"}
    assert "untranslated" in {p.code for p in validate("警報", "Alarm 監視", [], (), "ja", "en")}


def test_network_guard_blocks_external_but_allows_loopback() -> None:
    from sbt.privacy import network_guard
    network_guard.install()
    with socket.socket() as s, pytest.raises(network_guard.OfflineViolation):
        s.connect(("93.184.216.34", 80))
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    with socket.socket() as c:
        c.connect(server.getsockname())
    server.close()


def test_pptx_roundtrip_is_lossless(tmp_path: Path) -> None:
    from sbt.parsers.pptx_parser import PptxParser
    from sbt.renderers.pptx_renderer import PptxRenderer
    src = ROOT / "eval" / "testset" / "sample_en.pptx"
    if not src.exists():
        pytest.skip("run scripts/make_test_decks.py first")
    model = PptxParser().parse(src)
    for s in model.segments:
        s.translation = s.source
    out = tmp_path / "out.pptx"
    PptxRenderer("en", "en").render(model, out)
    again = PptxParser().parse(out)
    assert [(s.id, s.source) for s in again.segments] == [(s.id, s.source) for s in model.segments]


def test_renderer_refuses_to_overwrite_original() -> None:
    from sbt.parsers.pptx_parser import PptxParser
    from sbt.renderers.pptx_renderer import PptxRenderer
    src = ROOT / "eval" / "testset" / "sample_en.pptx"
    if not src.exists():
        pytest.skip("run scripts/make_test_decks.py first")
    with pytest.raises(ValueError):
        PptxRenderer("en", "ja").render(PptxParser().parse(src), src)


def test_restore_parentheses_and_tidy() -> None:
    src = "Variable Air Volume (VAV) terminal control"
    assert tok.restore_parentheses(src, "可変風量VAVターミナル制御", ["VAV"], "ja") == "可変風量（VAV）ターミナル制御"
    assert tok.restore_parentheses(src, "Variable air volume VAV terminal", ["VAV"], "en") == \
        "Variable air volume (VAV) terminal"
    assert tok.restore_parentheses("EMS (EMS)", "管理システム((EMS))", ["EMS"], "ja") == "管理システム(EMS)"
    assert tok.tidy("30–70 %RH at 24 °C", "30～70％RH、24 °C", "ja") == "30～70%RH、24℃"
    assert tok.tidy("24 °C", "24℃", "en") == "24 °C"
    assert tok.tidy("x", "edge device", "en") == "Edge device"
    assert tok.tidy("x", "iPhone app", "en") == "iPhone app"


def test_foreign_script_detected() -> None:
    codes = {p.code for p in validate("Field controllers communicate", "コントローラー들は通信します", [], (),
                                      "en", "ja")}
    assert "foreign_script" in codes


def test_inject_terms() -> None:
    from sbt.terminology.glossary import inject
    hints = (Hint("Air Handling Unit", "空調機", False), Hint("AHU", "AHU", True))
    assert inject("<g1>Air Handling Unit</g1> (AHU) control", hints) == "<g1>空調機</g1> (AHU) control"


def test_retag_puts_formatting_back() -> None:
    from sbt.pipeline.tags import retag
    src = "Model <g1>FX-PCG2611-0</g1> controller with <g2>setpoint</g2>"
    out = retag(src, "設定値付きのFX-PCG2611-0コントローラー", {"FX-PCG2611-0": "FX-PCG2611-0", "setpoint": "設定値"})
    assert out == "<g2>設定値</g2>付きの<g1>FX-PCG2611-0</g1>コントローラー"
    assert retag("<g1>foo</g1> bar", "バー", {}) is None


def test_extra_tag_spans_are_rejected() -> None:
    codes = {p.code for p in validate("<g1>Alarm</g1> and status", "<g1>警報</g1>と<g1>状態</g1>", [], (), "en", "ja")}
    assert "tags" in codes


def test_native_digits_count_as_numbers() -> None:
    assert tok.significant_numbers("၂၀၂၆ ခုနှစ် ၁၈%") == {"2026", "18"}


def test_paragraph_without_runs_is_handled() -> None:
    from lxml import etree
    from sbt.parsers.pptx_walk import encode_paragraph
    A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    empty = etree.fromstring(f'<a:p xmlns:a="{A}"><a:pPr/><a:endParaRPr lang="en-US"/></a:p>')
    assert encode_paragraph(empty).text == ""
    only_br = etree.fromstring(f'<a:p xmlns:a="{A}"><a:br/></a:p>')
    assert encode_paragraph(only_br).text == "\n"
