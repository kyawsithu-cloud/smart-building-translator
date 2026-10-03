# Development

## Environment (Windows 11)
- Python 3.13 (`py -3.13 -m venv .venv`, then `.venv\Scripts\activate`)
- `pip install -e .[dev]`
- `python -m pytest` (no model needed), `python -m ruff check src scripts tests`
- No Node.js needed: the UI is plain HTML/CSS/JavaScript modules without a build step.

## Layout
```
src/sbt/
  cli/          python -m sbt <command>: translate, check, glossary, history, doctor, ui (thin; no logic)
  app/          jobs.py (one document end to end), checks.py (check a translation made elsewhere),
                reports.py (report/review/terms files)
  quality/      independent checks of a finished translation: completeness, terminology, identifiers,
                output_check (reads the written file back), fonts, compare (pairs original + translation)
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
  winfonts.py   installed Windows fonts, font faces, theme fonts per script
  ui/           desktop app back end: app.py (window, drag & drop), api.py (functions the page calls),
                runner.py (job thread, progress, cancel), review.py, pages.py (side-by-side pictures),
                downloads.py, settings_store.py
  settings.py   config/default.toml + %LOCALAPPDATA%\SmartBuildingTranslator\settings.toml
  langdetect.py offline language detection
  languages.py  language registry (add a language here)
ui/             the page: index.html, css/app.css, js/app.js (router), js/views/*.js (one per screen),
                js/mock-api.js (sample data for previewing in a browser)
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

## Working on the UI
- Run the app: `python -m sbt ui` (add `--debug` for the WebView2 developer tools).
- Preview without Python or models: `python -m http.server 8770 --bind 127.0.0.1 --directory ui`, then open
  `http://127.0.0.1:8770/index.html?mock`. `?mock` swaps the Python bridge for `js/mock-api.js`.
- Every function the page calls is a method of `sbt.ui.api.Api` and returns plain JSON data. Attributes of `Api`
  must start with `_` (pywebview exposes public attributes to JavaScript).
- The page's content security policy (`index.html`) allows nothing outside the app: keep it that way. No CDN
  scripts, fonts or images; icons are inline SVG (`js/icons.js`).
- Document text is inserted with `textContent` only, never as HTML.

## Quality checks
- Each check returns `Finding`s (`src/sbt/quality/findings.py`): `message` never contains document text (it goes
  to `.report.json`), `detail` may (shown in the app, written to the review sheet).
- Measure every change: `python scripts/qc_eval.py` injects known errors into correct translations, lists every
  warning on clean translations for review, and compares overflow warnings with PowerPoint's own layout
  (`scripts/measure_text.ps1`, needs PowerPoint). Thresholds were tuned on the Phase 2–3 outputs; the Phase 1
  outputs are the held-out set — keep it that way.

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
