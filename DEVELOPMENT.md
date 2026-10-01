# Development

## Environment (Windows 11)
- Python 3.12 or 3.13 (`py -3.13 -m venv .venv` then `.venv\Scripts\activate`)
- `pip install -e .[dev]`
- Node 20+ only needed from Phase 4 (UI).

## Layout
```
src/sbt/        Python core (library + CLI). No UI code here.
  domain/       dataclasses shared by all layers
  parsers/      DocumentParser implementations (pptx, pdf, ocr)
  renderers/    DocumentRenderer implementations + text fitting
  pipeline/     orchestration of protect → glossary → context → engine → validate
  protection/   protected-token masking
  terminology/  glossary loading/matching
  engines/      TranslationEngine interface + implementations
  models_mgr/   local model catalogue / download / verify
  quality/      QA checks
  storage/      SQLite schema + repositories
  privacy/      NetworkGuard, log redaction
  hardware/     CPU/RAM/GPU probing
  poc/          Phase 1 CLI (throwaway-quality allowed, isolated)
ui/             Phase 4 web UI (TypeScript), hosted in WebView2
data/           seed glossary
eval/           test set + results (public, non-confidential content only)
tests/          unit + integration
```

## Conventions
- Small modules, typed (`mypy --strict` on `src/`), `ruff` for lint/format.
- Dependencies point inward: engines/parsers/renderers depend on `domain`, never on each other.
- **Never log document text.** Use `sbt.privacy` helpers; log counts, ids, timings.
- Secrets from environment variables only.
- Tests must use generated/public documents only.

## Adding a translation provider
1. Implement `TranslationEngine` (`src/sbt/engines/base.py`); set `EngineInfo.is_local` truthfully.
2. Register it in the engine registry with a config key.
3. If `is_local=False`, it is automatically hidden in offline mode and requires the consent flow.
4. Add an integration test against the public eval deck.

## Building the Windows app (Phase 6, planned)
PyInstaller (onedir) bundling Python core + built UI + `llama-server.exe`, wrapped with an Inno Setup installer
→ `SmartBuildingTranslator.exe`. Models are downloaded on demand, not bundled.
