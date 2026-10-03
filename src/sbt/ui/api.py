"""Functions the window can call (window.pywebview.api.*). Everything returns plain JSON-able data.

Kept thin: real work happens in sbt.app / sbt.storage / sbt.ui.* modules. Attributes that must not be exposed
to JavaScript start with an underscore (pywebview walks public attributes).
"""
from __future__ import annotations

import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from sbt import formats, langdetect, languages
from sbt import settings as settings_mod
from sbt.app import checks
from sbt.app.jobs import JobSpec
from sbt.domain.models import DocumentError
from sbt.engines.llama_server import RUNTIME, model_path
from sbt.engines.profiles import PROFILES
from sbt.hardware.probe import detect
from sbt.hardware.recommend import recommend
from sbt.quality.terminology import OTHER
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.storage.jobs_repo import JobRepo
from sbt.storage.memory import TranslationMemory
from sbt.terminology.glossary import Term
from sbt.ui import downloads, pages, review, settings_store
from sbt.ui.runner import JobRunner

VERSION = "0.5.0"
EXPLAIN = {
    "overflow": "text may not fit its box even after shrinking",
    "font_reduced": "text box font reduced to fit",
    "term_missing": "required glossary term not used",
    "token_missing": "identifier or number changed",
    "untranslated": "paragraph left in the original language",
    "empty": "paragraph could not be translated",
    "tags": "formatting simplified to one style",
    "foreign_script": "characters from another language",
    "number_mismatch": "a number may have changed",
    "length_suspicious": "translation unusually short or long",
    "term_inconsistent": "glossary term translated inconsistently",
    "parentheses_lost": "brackets around an acronym dropped",
    "added_text": "model added text",
}


class Api:
    def __init__(self, runner: JobRunner | None = None) -> None:
        self._window: Any = None                  # set by app.py; private so pywebview does not expose it
        self._runner = runner or JobRunner()
        self._downloader = downloads.Downloader()

    # --- helpers --------------------------------------------------------------------------------------
    @staticmethod
    def _settings() -> settings_mod.Settings:
        return settings_mod.load()

    def _conn(self):  # type: ignore[no-untyped-def]
        return db.connect(self._settings().db_path)

    # --- app ------------------------------------------------------------------------------------------
    def app_info(self) -> dict[str, object]:
        s = self._settings()
        conn = self._conn()
        try:
            repo = GlossaryRepo(conn)
            repo.ensure(s.glossary)
            names = repo.names()
        finally:
            conn.close()
        return {
            "version": VERSION, "mode": "offline",
            "languages": [{"code": c, "name": lang.name} for c, lang in languages.LANGUAGES.items()],
            "glossaries": names, "settings": settings_store.current(),
            "engine_installed": (RUNTIME / "llama" / "llama-server.exe").exists(),
            "model_installed": model_path(PROFILES[s.model]).exists(),
            "data_dir": str(settings_mod.data_dir()),
        }

    # --- choosing a file --------------------------------------------------------------------------------
    def choose_file(self) -> str | None:
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                                 file_types=("Documents (*.pptx;*.pdf)", "All files (*.*)"))
        return str(result[0]) if result else None

    def inspect_file(self, path: str) -> dict[str, object]:
        """Quick look at a file before translating: type, size, detected language, suggested output name."""
        p = Path(path)
        if not p.is_file():
            raise DocumentError("File not found.")
        formats.check_supported(p)
        model = formats.parser_for(p, None, ocr=False).parse(p)
        text = "\n".join(s.plain_source for s in model.segments)
        notes = list(model.notices)
        if not text.strip() and p.suffix.lower() == ".pdf":
            text = _ocr_first_page(p)
            notes.append("Scanned PDF: the text will be read by OCR (check the result in Review).")
        found = langdetect.detect(text) if text.strip() else langdetect.Detection("en", 0.0)
        target = langdetect.default_target(found.language)
        return {"path": str(p), "name": p.name, "folder": str(p.parent), "type": p.suffix[1:].upper(),
                "size_kb": round(p.stat().st_size / 1024), "pages": model.container_count,
                "paragraphs": len(model.segments), "detected": found.language,
                "confidence": round(found.confidence, 2), "target": target, "notes": notes}

    # --- translation ------------------------------------------------------------------------------------
    def start_translation(self, request: dict[str, Any]) -> dict[str, object]:
        s = self._settings()
        src, tgt = request["source"], request["target"]
        languages.get(src), languages.get(tgt)
        if src == tgt:
            raise ValueError("Source and target language are the same.")
        path = Path(request["path"])
        formats.check_supported(path)
        out = path.with_name(f"{path.stem}_{tgt.upper()}{path.suffix}")
        s.glossary = request.get("glossary") or s.glossary
        spec = JobSpec(path, out, src, tgt, s.model, s.repair_model, s.protect, s.doc_terms, s.min_font_scale,
                       ocr=request.get("ocr", True))
        pages.clear_cache()
        self._runner.start(spec, s, use_memory=request.get("memory", True))
        return {"output": str(out)}

    def start_check(self, request: dict[str, Any]) -> None:
        """Quality-check a translation made elsewhere: request = {original, translation, source, target,
        use_model}."""
        s = self._settings()
        src, tgt = request["source"], request["target"]
        languages.get(src), languages.get(tgt)
        if src == tgt:
            raise ValueError("The original and the translation are in the same language.")
        original, translation = Path(request["original"]), Path(request["translation"])
        if original.resolve() == translation.resolve():
            raise ValueError("Choose two different files: the original and its translation.")
        for path in (original, translation):
            formats.check_supported(path)
        s.glossary = request.get("glossary") or s.glossary
        spec = checks.CheckSpec(original, translation, src, tgt, s.model, use_model=request.get("use_model", True))
        pages.clear_cache()
        self._runner.start(spec, s, use_memory=False, run=checks.run_check)  # type: ignore[arg-type]

    def export_checks(self) -> str | None:
        import webview
        job = self._runner.job
        if job is None:
            return None
        name = f"{Path(job.spec.output).stem}.checks.csv"
        result = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name,
                                                 file_types=("CSV (*.csv)",))
        if not result:
            return None
        target = Path(result if isinstance(result, str) else result[0])
        if isinstance(job, checks.CheckJob):
            job.write_csv(target)
        else:
            checks.write_findings_csv(job.doc, job.quality, target)
        return str(target)

    def job_status(self) -> dict[str, object]:
        state = self._runner.state.as_dict()
        if state["status"] == "done" and self._runner.job is not None:
            state["result"] = self._summary()
        return state

    def cancel(self) -> None:
        self._runner.cancel()

    def _summary(self) -> dict[str, object]:
        job = self._runner.job
        assert job is not None
        r = job.report
        quality = {"summary": job.quality.summary(), "checked": job.quality.checked,
                   "findings": review.findings(job)}
        if isinstance(job, checks.CheckJob):
            return {"kind": "check", "input": str(job.spec.input), "output": str(job.spec.output),
                    "output_name": job.spec.output.name, "source": r["source_lang"], "target": r["target_lang"],
                    "segments": r["segments"], "matched": r["matched"], "seconds": r["seconds"],
                    "term_note": job.term_note, "notices": r.get("notices") or [],
                    "flagged": len(job.quality.flagged_segments()), "quality": quality}
        issues = [i for i in r["issues"] if i["severity"] != "info"]  # type: ignore[union-attr,index]
        info = [i for i in r["issues"] if i["severity"] == "info"]  # type: ignore[union-attr,index]
        warnings = [{"count": n, "text": EXPLAIN.get(code, code), "code": code}
                    for code, n in Counter(i["code"] for i in issues).most_common()]
        untranslatable = Counter(str(u).split(":", 1)[-1].strip() for u in r.get("untranslatable") or [])
        return {
            "kind": "translation",
            "input": str(job.spec.input), "output": str(job.spec.output), "output_name": job.spec.output.name,
            "source": r["source_lang"], "target": r["target_lang"], "segments": r["segments"],
            "translated_pct": r["translated_pct"], "seconds": r["seconds"],
            "checks": {"identifiers": r["protected_token_integrity_pct"], "glossary": r["glossary_adherence_pct"],
                       "formatting": r["tag_integrity_pct"]},
            "warnings": warnings, "font_reduced": len(info),
            "not_translatable": [{"count": n, "text": t} for t, n in untranslatable.items()],
            "notices": r.get("notices") or [], "ocr_segments": r.get("ocr_segments", 0),
            "doc_terms": r.get("doc_terms", 0), "doc_terms_unresolved": r.get("doc_terms_unresolved", 0),
            "repaired": r.get("repaired", 0), "edited": r.get("edited_by_user", 0),
            "flagged": len(job.quality.flagged_segments()), "quality": quality,
        }

    def open_result(self, what: str) -> None:
        """Open the translated file, its folder, or a companion file (review/terms CSV)."""
        job = self._runner.job
        if job is None:
            return
        out = job.spec.output
        targets = {"file": out, "review": out.with_suffix(".review.csv"), "terms": out.with_suffix(".terms.csv"),
                   "original": job.spec.input}
        if what == "folder":
            subprocess.Popen(["explorer", "/select,", str(out)])
        elif what in targets and targets[what].exists():
            os.startfile(targets[what])  # type: ignore[attr-defined]

    # --- review -----------------------------------------------------------------------------------------
    def review_items(self) -> list[dict[str, object]]:
        job = self._runner.job
        return review.items(job) if job else []

    def check_edit(self, segment_id: str, text: str) -> list[str]:
        job = self._runner.job
        if job is None:
            return []
        return review.check_edit(job, segment_id, text)[1]

    def save_edit(self, segment_id: str, text: str) -> dict[str, object]:
        job = self._runner.job
        if job is None or isinstance(job, checks.CheckJob):
            raise ValueError("This translation cannot be edited here.")
        tagged, warnings = review.check_edit(job, segment_id, text)
        job.apply_edit(segment_id, tagged)
        job.check_quality()
        return {"warnings": warnings, "translation": review.to_display(tagged)}

    def page_view(self, page: int) -> dict[str, object]:
        """Original and translated page as images, with the flagged paragraphs outlined."""
        job = self._runner.job
        if job is None:
            raise ValueError("Nothing to compare yet.")
        return pages.page_view(job.doc, job.quality, job.spec.input, job.spec.output, int(page))

    def review_findings(self) -> list[dict[str, object]]:
        job = self._runner.job
        return review.findings(job) if job else []

    def apply_variant(self, index: int, chosen: str) -> int:
        """Make a term or a repeated text consistent: use `chosen` in every paragraph of finding `index`.
        Only exact occurrences of the other known wordings are replaced; 'other wording' is left for the user."""
        job = self._runner.job
        if job is None or isinstance(job, checks.CheckJob):
            raise ValueError("This translation cannot be edited here.")
        f = job.quality.sorted()[int(index)]
        variants = f.detail.get("variants") or {}
        changed = 0
        if f.code == "term_variants":
            for variant, ids in variants.items():  # type: ignore[union-attr]
                if variant in (chosen, OTHER):
                    continue
                for sid in ids:
                    seg = next(x for x in job.doc.segments if x.id == sid)
                    if seg.translation and variant in seg.translation:
                        job.apply_edit(sid, seg.translation.replace(variant, chosen))
                        changed += 1
        elif f.code == "same_source_differs":
            model = next((x for x in job.doc.segments if x.id in variants.get(chosen, [])), None)  # type: ignore[union-attr]
            if model is None or model.translation is None:
                raise ValueError("Unknown translation.")
            for sid in f.segments:
                seg = next(x for x in job.doc.segments if x.id == sid)
                if seg.translation != model.translation:
                    same_tags = seg.source == model.source
                    job.apply_edit(sid, model.translation if same_tags else review.strip_display_tags(
                        model.translation))
                    changed += 1
        else:
            raise ValueError("This check cannot be fixed automatically.")
        job.check_quality()
        return changed

    def rebuild(self) -> dict[str, object]:
        """Write the document again with the user's edits (no re-translation)."""
        job = self._runner.job
        if job is None or isinstance(job, checks.CheckJob):
            raise ValueError("No translation to rebuild.")
        job.finish()
        return self._summary()

    # --- glossary ---------------------------------------------------------------------------------------
    def glossary_terms(self, name: str, search: str = "") -> list[dict[str, object]]:
        conn = self._conn()
        try:
            return [{"id": st.id, **st.term.__dict__, "draft": "DRAFT" in st.term.notes}
                    for st in GlossaryRepo(conn).terms(name, search)]
        finally:
            conn.close()

    def glossary_save(self, name: str, term: dict[str, Any]) -> int:
        t = Term(term["source_term"].strip(), (term.get("target_term") or term["source_term"]).strip(),
                 term.get("source_lang", "en"), term.get("target_lang", "ja"), term.get("category", ""),
                 term.get("notes", ""), bool(term.get("do_not_translate")), term.get("priority", "normal"),
                 term.get("context", ""))
        if not t.source_term:
            raise ValueError("The source term is empty.")
        languages.get(t.source_lang), languages.get(t.target_lang)
        conn = self._conn()
        try:
            repo = GlossaryRepo(conn)
            if term.get("id"):
                repo.update(int(term["id"]), **{k: v for k, v in t.__dict__.items()})
                return int(term["id"])
            return repo.add(name, t)
        finally:
            conn.close()

    def glossary_delete(self, term_id: int) -> bool:
        conn = self._conn()
        try:
            return GlossaryRepo(conn).delete(int(term_id))
        finally:
            conn.close()

    def glossary_import(self, name: str) -> int:
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("CSV (*.csv)",))
        if not result:
            return 0
        conn = self._conn()
        try:
            return GlossaryRepo(conn).import_csv(name, Path(result[0]))
        finally:
            conn.close()

    def glossary_import_terms_of_last_job(self, name: str) -> int:
        job = self._runner.job
        path = job.spec.output.with_suffix(".terms.csv") if job else None
        if path is None or not path.exists():
            raise ValueError("The last translation has no term sheet.")
        conn = self._conn()
        try:
            return GlossaryRepo(conn).import_csv(name, path)
        finally:
            conn.close()

    def glossary_export(self, name: str) -> str | None:
        import webview
        result = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"{name}.csv",
                                                 file_types=("CSV (*.csv)",))
        if not result:
            return None
        target = Path(result if isinstance(result, str) else result[0])
        conn = self._conn()
        try:
            GlossaryRepo(conn).export_csv(name, target)
        finally:
            conn.close()
        return str(target)

    # --- history ----------------------------------------------------------------------------------------
    def history(self) -> dict[str, object]:
        conn = self._conn()
        try:
            rows = [dict(r) for r in JobRepo(conn).recent(50)]
            return {"jobs": rows, "memory": TranslationMemory(conn).count(), "data_dir": str(settings_mod.data_dir())}
        finally:
            conn.close()

    def clear_history(self) -> dict[str, int]:
        conn = self._conn()
        try:
            return {"jobs": JobRepo(conn).clear(), "memory": TranslationMemory(conn).clear()}
        finally:
            conn.close()

    # --- models & hardware ------------------------------------------------------------------------------
    def system(self) -> dict[str, object]:
        hw = detect()
        s = self._settings()
        rec = recommend(hw, s.model)
        return {
            "hardware": {"os": hw.os, "cpu": hw.cpu, "cores": hw.cores, "ram_gib": hw.ram_gib,
                         "gpus": [g.__dict__ for g in hw.gpus]},
            "recommendation": {"model": rec.model, "placement": rec.placement, "expectation": rec.expectation,
                               "notes": list(rec.notes)},
            "items": [{**i.__dict__, "installed": downloads.installed(i.id), "deletable": downloads.deletable(i.id),
                       "languages": sorted(PROFILES[i.id].languages) if i.id in PROFILES else []}
                      for i in downloads.CATALOGUE],
            "download": self._downloader.state.__dict__,
        }

    def download(self, item_id: str) -> None:
        self._downloader.start(item_id)

    def download_status(self) -> dict[str, object]:
        return dict(self._downloader.state.__dict__)

    def delete_model(self, item_id: str) -> None:
        if self._runner.busy:
            raise RuntimeError("Wait until the translation has finished.")
        downloads.delete(item_id)

    # --- settings ---------------------------------------------------------------------------------------
    def get_settings(self) -> dict[str, object]:
        return settings_store.current()

    def save_settings(self, changes: dict[str, Any]) -> dict[str, object]:
        return settings_store.save(changes)


def _ocr_first_page(path: Path) -> str:
    import numpy as np
    import pymupdf

    from sbt.ocr import engine
    with pymupdf.open(path) as doc:
        pix = doc[0].get_pixmap(dpi=150, colorspace=pymupdf.csRGB, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    try:
        return "\n".join(ln.text for ln in engine.read(img, "en"))
    except engine.OcrUnavailable:
        return ""
