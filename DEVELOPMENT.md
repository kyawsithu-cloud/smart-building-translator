# Development

## Environment (Windows 11)
- Python 3.13 (`py -3.13 -m venv .venv`, then `.venv\Scripts\activate`)
- `pip install -e .[dev]`
- `python -m pytest` (no model needed), `python -m ruff check src scripts tests`
- Node 20+ only from Phase 4 (UI).

## Layout
```
src/sbt/
  cli/          python -m sbt <command>: translate, glossary, history, doctor (thin; no logic)
  app/          jobs.py (one document end to end), reports.py (report/review/terms files)
  domain/       dataclasses shared by all layers
  formats.py    which parser/renderer handles which file type
  parsers/      PPTX traversal (incl. charts, SmartArt, pictures) + parser; PDF parser (text, tables, scans)
  renderers/    PPTX writer + text fitting; PDF writer (redact + re-layout); fonts per language
  ocr/          offline OCR wrapper (RapidOCR), paragraph grouping, Japanese OCR clean-up
  pipeline/     translator.py (passes, retries, harmonise, repair), validate.py, tags.py
  terminology/  glossary.py (matching, context, priority), term_sheet.py (recurring document terms)
  protection/   identifiers that must survive, tidy-up, parenthesis repair
  engines/      TranslationEngine interface, llama.cpp client, server lifecycle, prompts, model profiles
  storage/      SQLite: schema, glossaries, translation memory, job history
  hardware/     detection (CPU/RAM/GPU) and model recommendation
  privacy/      NetworkGuard
  settings.py   config/default.toml + %LOCALAPPDATA%\SmartBuildingTranslator\settings.toml
  langdetect.py offline language detection
  languages.py  language registry (add a language here)
scripts/        model download, test decks/PDFs, evaluation (translation, consistency, OCR), rendering
eval/           public test decks and results (never put real documents here)
tests/unit/     fast tests; pipeline tests use a fake engine
```

## Conventions
- Small modules, typed, `ruff` clean.
- Dependencies point inward: engines/parsers/renderers/storage depend on `domain`, not on each other.
- **Never log document text.** Log counts, ids, timings. Reports (`.report.json`) contain no text.
- Measure before changing defaults: run `scripts/run_eval.py` (and `consistency_eval.py`) before and after.
- Secrets from environment variables only (none are needed today).
- Tests use generated or public documents only.

## Adding a model
1. Add a pinned entry (URL + SHA-256) to `scripts/download_phase1.py`.
2. Add a `ModelProfile` to `src/sbt/engines/profiles.py`: file, prompt style, languages it is *trusted* for,
   context size, sampling.
3. If it needs its own prompt format, add a builder in `src/sbt/engines/prompts.py`.
4. Run the evaluation; record the results before making it a default.

## Adding a translation provider
1. Implement `TranslationEngine` (`src/sbt/engines/base.py`); set `EngineInfo.is_local` truthfully.
2. A provider with `is_local=False` must not be constructible in offline mode, and needs the per-job consent
   flow described in PRIVACY.md (not built yet).

## Building the Windows app (Phase 6, planned)
PyInstaller (onedir) bundling the Python core + UI + `llama-server.exe`, wrapped with an Inno Setup installer
→ `SmartBuildingTranslator.exe`. Models downloaded on demand, not bundled.
