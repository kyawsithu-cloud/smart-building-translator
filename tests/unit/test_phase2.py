from __future__ import annotations

from pathlib import Path

import pytest

from sbt import langdetect
from sbt.domain.models import DocumentModel, Segment, SegmentKind
from sbt.engines.base import EngineInfo, EngineStats, TranslationRequest, TranslationResult
from sbt.pipeline.tags import strip_tags
from sbt.pipeline.translator import PipelineOptions, TranslationPipeline
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.storage.jobs_repo import JobRepo
from sbt.storage.memory import TranslationMemory
from sbt.terminology import term_sheet
from sbt.terminology.glossary import Glossary, Hint, Term

ROOT = Path(__file__).resolve().parents[2]


class FakeEngine:
    """Dictionary 'translator': replaces known phrases, so tests can assert exactly what the pipeline did."""

    def __init__(self, table: dict[str, str], name: str = "fake") -> None:
        self.table = table
        self.stats = EngineStats()
        self.requests: list[TranslationRequest] = []
        self.name = name

    @property
    def info(self) -> EngineInfo:
        return EngineInfo(self.name, self.name, True, frozenset({"en", "ja"}))

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.requests.append(request)
        out = {}
        for item in request.items:
            text = item.text
            for k in sorted(self.table, key=len, reverse=True):
                text = text.replace(k, self.table[k])
            out[item.id] = text
        return TranslationResult(out, [])


def _doc(*texts: str) -> DocumentModel:
    segs = [Segment(f"s{i + 1}/1/p0", SegmentKind.BODY, i + 1, f"s{i + 1}/1", t) for i, t in enumerate(texts)]
    return DocumentModel("x.pptx", "pptx", len(texts), segs)


# --- storage ------------------------------------------------------------------------------------------------
def test_glossary_repo_seed_crud_import_export(tmp_path: Path) -> None:
    repo = GlossaryRepo(db.connect(tmp_path / "t.db"))
    seeded = repo.terms("smart-building")
    assert len(seeded) > 30                                         # seeded from the project CSV once
    tid = repo.add("smart-building", Term("supply air", "給気", "en", "ja", priority="high"))
    assert repo.update(tid, target_term="給気温度", context="temperature")
    assert any(st.term.target_term == "給気温度" for st in repo.terms("smart-building", "supply"))
    out = tmp_path / "export.csv"
    n = repo.export_csv("smart-building", out)
    other = GlossaryRepo(db.connect(tmp_path / "other.db"))
    assert other.import_csv("copy", out) == n
    assert len(other.terms("copy")) == n
    assert repo.delete(tid) and not repo.delete(tid)
    with pytest.raises(ValueError):
        repo.update(1, bogus="x")


def test_import_rejects_bad_rows(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("source_term,target_term,source_lang,target_lang\nfoo,,en,ja\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Row 2"):
        GlossaryRepo(db.connect(tmp_path / "t.db")).import_csv("x", bad)


def test_memory_exact_similar_clear_and_disabled(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "t.db")
    tm = TranslationMemory(conn)
    tm.store("en", "ja", "Energy saving control is enabled.", "省エネ制御が有効です。", "m")
    tm.store("en", "ja", "Energy saving control is enabled.", "省エネルギー制御が有効です。", "m", origin="human")
    tm.commit()
    assert tm.exact("en", "ja", "Energy saving control is enabled.").origin == "human"   # human wins
    similar = tm.similar("en", "ja", "Energy saving control is disabled.")
    assert similar and similar[0].target.startswith("省エネ")
    assert tm.similar("en", "ja", "Completely unrelated text about blinds") == []
    off = TranslationMemory(conn, enabled=False)
    off.store("en", "ja", "a", "b", "m")
    assert off.exact("en", "ja", "Energy saving control is enabled.") is None
    assert tm.clear() == 2 and tm.count() == 0


def test_job_history_has_no_document_text(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "t.db")
    JobRepo(conn).record({"file": "deck.pptx", "source_lang": "en", "target_lang": "ja", "model": "m",
                          "mode": "offline", "segments": 3, "translated_segments": 3, "issues": [], "seconds": 1.0})
    cols = [r[1] for r in conn.execute("PRAGMA table_info(translation_jobs)")]
    assert not any("text" in c for c in cols)
    assert JobRepo(conn).clear() == 1


# --- glossary context ---------------------------------------------------------------------------------------
def test_context_dependent_entry_wins_only_in_context() -> None:
    g = Glossary([Term("alarm", "警報", "en", "ja"),
                  Term("alarm", "アラーム", "en", "ja", context="screen, display")])
    assert g.match("Alarm list", "en", "ja") == [Hint("alarm", "警報", False)]
    assert g.match("Alarm list", "en", "ja", context_text="Operator screen layout") == \
        [Hint("alarm", "アラーム", False)]


def test_priority_breaks_ties() -> None:
    g = Glossary([Term("chiller", "チラー", "en", "ja", priority="low"),
                  Term("chiller", "冷凍機", "en", "ja", priority="high", context="")])
    assert g.match("chiller plant", "en", "ja")[0].target == "冷凍機"


# --- language detection -------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,lang", [
    ("ビル管理システムは空調設備を監視します。", "ja"),
    ("建筑管理系统监控暖通空调设备。", "zh"),
    ("빌딩 관리 시스템은 공조 설비를 감시합니다.", "ko"),
    ("ระบบจัดการอาคารตรวจสอบอุปกรณ์", "th"),
    ("အဆောက်အအုံ စီမံခန့်ခွဲမှုစနစ်", "my"),
    ("The building management system monitors the HVAC equipment.", "en"),
    ("Das Gebäudeleitsystem überwacht die Anlagen und die Sensoren.", "de"),
    ("Le système de gestion technique du bâtiment surveille les équipements.", "fr"),
    ("El sistema de gestión del edificio supervisa los equipos y la red.", "es"),
])
def test_langdetect(text: str, lang: str) -> None:
    assert langdetect.detect(text).language == lang


def test_bullet_only_english_defaults_to_english() -> None:
    assert langdetect.detect("Occupancy sensor\nCO2 sensor\nGateway").language == "en"


# --- term sheet ---------------------------------------------------------------------------------------------
def test_term_sheet_mines_recurring_non_glossary_phrases() -> None:
    doc = _doc("The chilled water plant runs at night.", "Chilled water plant efficiency",
               "Optimise the chilled water plant schedule.", "The Building Management System monitors it.",
               "Building Management System overview")
    glossary = Glossary([Term("Building Management System", "ビル管理システム", "en", "ja")])
    terms = [t.source for t in term_sheet.mine(doc.segments, "en", "ja", glossary)]
    assert "chilled water plant" in terms
    assert not any("building management" in t for t in terms)       # glossary terms are not mined again
    assert not any(t in ("chilled water", "water plant") for t in terms)   # maximal phrase only


def test_term_sheet_japanese() -> None:
    doc = _doc("冷水プラントの運転を最適化", "冷水プラント効率", "夜間の冷水プラント運転")
    terms = [t.source for t in term_sheet.mine(doc.segments, "ja", "en", Glossary([]))]
    assert "冷水プラント" in terms


# --- pipeline ------------------------------------------------------------------------------------------------
def test_pipeline_uses_term_sheet_and_memory(tmp_path: Path) -> None:
    engine = FakeEngine({"chilled water plant": "冷水プラント", "Chilled water plant": "冷水プラント",
                         "The": "", "runs at night": "は夜間運転", "efficiency": "効率", ".": "。"})
    doc = _doc("The chilled water plant runs at night.", "Chilled water plant efficiency")
    tm = TranslationMemory(db.connect(tmp_path / "t.db"))
    pipe = TranslationPipeline(engine, Glossary([]), PipelineOptions("en", "ja", doc_terms="hint"), tm)
    result = pipe.run(doc)
    assert result.term_sheet and [t.source for t in result.term_sheet.terms] == ["chilled water plant"]
    hinted = [h for r in engine.requests for it in r.items for h in it.hints if h.origin == "document"]
    assert hinted, "document terms must reach the engine as hints"
    assert result.doc_term_checks == 2 and result.doc_term_hits == 2

    # Second run of the same deck: everything comes from memory, the engine translates nothing.
    engine2 = FakeEngine({})
    doc2 = _doc("The chilled water plant runs at night.", "Chilled water plant efficiency")
    result2 = TranslationPipeline(engine2, Glossary([]), PipelineOptions("en", "ja", doc_terms="off"), tm).run(doc2)
    assert {o.status for o in result2.outcomes.values()} == {"memory"}
    assert [strip_tags(s.translation or "") for s in doc2.segments] == \
           [strip_tags(s.translation or "") for s in doc.segments]


def test_memory_hit_is_rejected_when_glossary_changed(tmp_path: Path) -> None:
    tm = TranslationMemory(db.connect(tmp_path / "t.db"))
    tm.store("en", "ja", "chiller alarm", "チラー警報", "m")
    engine = FakeEngine({"chiller": "冷凍機", "alarm": "警報", " ": ""})
    glossary = Glossary([Term("chiller", "冷凍機", "en", "ja")])
    doc = _doc("chiller alarm")
    TranslationPipeline(engine, glossary, PipelineOptions("en", "ja", doc_terms="off"), tm).run(doc)
    assert doc.segments[0].translation == "冷凍機警報"            # stale memory entry not reused


def test_repair_engine_fixes_flagged_segment() -> None:
    bad = FakeEngine({"Gateway status": "Gateway status"}, "bad")       # leaves text untranslated
    good = FakeEngine({"Gateway status": "ゲートウェイの状態"}, "good")
    doc = _doc("Gateway status")
    pipe = TranslationPipeline(bad, Glossary([]), PipelineOptions("en", "ja", doc_terms="off"))
    result = pipe.run(doc)
    assert result.outcomes[doc.segments[0].id].status == "failed"
    assert pipe.repair(doc, good, result) == 1
    assert result.outcomes[doc.segments[0].id].status == "repaired"
    assert doc.segments[0].translation == "ゲートウェイの状態"


def test_settings_load_defaults_and_user_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sbt import settings
    monkeypatch.setenv("SBT_DATA_DIR", str(tmp_path))
    assert settings.load().model == "hy-mt2-7b"
    (tmp_path / "settings.toml").write_text('model = "qwen3-8b"\n[translation]\ndoc_terms = "off"\n',
                                            encoding="utf-8")
    s = settings.load()
    assert (s.model, s.doc_terms, s.db_path) == ("qwen3-8b", "off", tmp_path / "sbt.db")
    (tmp_path / "settings.toml").write_text('mode = "online"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        settings.load()


def test_vote_mode_harmonises_minority_and_keeps_majority() -> None:
    engine = FakeEngine({"trend log": "トレンドログ", "Trend log interval": "傾向ログ間隔", "interval": "間隔",
                         "data A": "データA", "data B": "データB", " ": ""})
    doc = _doc("trend log data A", "trend log data B", "Trend log interval")
    pipe = TranslationPipeline(engine, Glossary([]), PipelineOptions("en", "ja", doc_terms="vote"))
    result = pipe.run(doc)
    term = next(t for t in result.term_sheet.all_terms if t.source == "trend log")
    assert term.target == "トレンドログ"                     # majority of in-sentence translations
    assert doc.segments[2].translation == "トレンドログ間隔"     # the deviating paragraph was re-translated
    assert result.outcomes[doc.segments[2].id].status == "harmonised" and result.harmonised == 1
    assert result.doc_term_hits == result.doc_term_checks == 3


def test_vote_mode_leaves_terms_without_majority_alone() -> None:
    engine = FakeEngine({"free cooling": "自由冷却", "Free cooling mode": "フリークーリングモード",
                         "Free cooling savings": "自然冷却による削減", " ": ""})
    doc = _doc("Free cooling mode", "Free cooling savings")
    result = TranslationPipeline(engine, Glossary([]), PipelineOptions("en", "ja")).run(doc)
    term = next(t for t in result.term_sheet.all_terms if t.source == "free cooling")
    assert term.target == "" and term.note == "no consistent translation found"
    assert [s.translation for s in doc.segments] == ["フリークーリングモード", "自然冷却による削減"]


def test_repair_skipped_for_unsupported_pair_or_missing_model() -> None:
    from sbt.app.jobs import JobSpec, repair_profile
    spec = JobSpec(Path("x.pptx"), Path("y.pptx"), "en", "my", repair_model="qwen3-8b")
    profile, why = repair_profile(spec)
    assert profile is None and "language pair" in why
    assert repair_profile(JobSpec(Path("x"), Path("y"), "en", "ja", repair_model="nope"))[0] is None


def test_term_matching_ignores_optional_spaces_in_non_latin_scripts() -> None:
    assert term_sheet.contains("အဆောက်အအုံ အလိုအလျောက်ထိန်းချုပ်စနစ်ကို", "အဆောက်အအုံအလိုအလျောက် ထိန်းချုပ်စနစ်", "my")
    assert term_sheet.contains("The Trend Log shows", "trend log", "en")
    assert not term_sheet.contains("トレンド記録", "トレンドログ", "ja")
