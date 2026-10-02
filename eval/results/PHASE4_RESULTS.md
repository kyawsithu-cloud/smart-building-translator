# Phase 4 Results: Desktop App

Date: 2026-10-02 · Hardware: Ryzen 7 5700X, 32 GB RAM, RTX 4060 8 GB · Windows 11 · WebView2 (Edge) via
pywebview 6.2 · Mode: offline. Test file: `eval/testset/sample_en.pptx` (generated, public).

## 1. What was built

| Screen | Contents |
|---|---|
| **Translate** | Drop a file on the window or *Browse…*; file card (type, pages, paragraphs, size, detected language); From/To with swap; glossary; Mode **Offline** (Online shown disabled); options (OCR, translation memory); progress steps with paragraph counter and Cancel; result with the four checks, warnings in plain words, *Open translated file*, *Open folder*, *Review translation*, *Term sheet* |
| **Review** | Original and translation side by side; filter *All / Needs a look / Edited*; search; click a translation to correct it (Ctrl+Enter saves); the automatic checks are re-run on the correction and shown as warnings; formatting markers shown as `[1]…[/1]`; *Save & rebuild document* writes the file again without re-translating; corrections go into the translation memory as human-approved |
| **Glossary** | Search, add, edit, delete terms (do-not-translate, priority, context words); import/export CSV; import the term sheet of the last translation |
| **History** | Recent translations (file name, languages, counts, time — no document text); translation-memory size; *Clear history* |
| **Models** | Processor, memory, GPU (VRAM free) and the recommendation; components with size, licence, installed state; *Download* (confirmation names source, SHA-256 check and Defender scan; runs in a separate process with progress) and *Delete* |
| **Settings** | Light / Dark / System theme; term consistency; repair model; GPU or CPU; translation memory; where data is stored |

Start: `start.bat` (no console window) or `python -m sbt ui`. Errors are shown as plain sentences
(engine not installed, output file open in PowerPoint, engine start timeout, damaged/protected file); other
errors show the error type only and are logged without document text.

## 2. Verification

| Check | Result |
|---|---|
| Unit tests | 69 pass (9 new: API flow with a fake engine, review edit + rebuild, tag markers, cancel, error messages without document text, settings validation, no public attributes exposed to JavaScript) |
| Real window, end to end (scripted through the page) | drop → file card → *Translate* → progress → result → Review → correction → rebuild → Glossary, History, Models, Settings: **all passed, 0 JavaScript errors, 0 error toasts** |
| Translation in the window | 63 paragraphs, 100 % translated, identifiers/glossary/formatting 100 %, 1 paragraph repaired by Qwen3, 41.5 s; all 7 progress stages reported |
| Rebuild after a correction | document rewritten with the correction, report shows `edited_by_user = 1`, original unchanged |
| Page security policy | `default-src 'self'`; scripts, styles, images and connections limited to the app itself; works with the pywebview bridge |
| Offline install | `pywebview`, `pythonnet`, `clr_loader`, `bottle`, `proxy_tools`, `cffi`, `pycparser` added to `runtime\wheels` (pinned, Windows Defender: no threats); `pip install --no-index --find-links runtime\wheels -e .` resolves |

Not automated: dragging a file from Explorer onto the window (needs a real mouse drag). The handler is
registered at start-up and its page side (`sbtFileDropped`) is exercised by the end-to-end run.

## 3. Privacy notes

- The page is served by pywebview from the `ui` folder on 127.0.0.1 only; the content security policy blocks
  every other address, and there are no external fonts, scripts or images (icons are inline SVG).
- WebView2 runs in private mode (no cache, cookies or history kept).
- Document text is put into the page with `textContent` only (never parsed as HTML).
- Model downloads run in a separate process, only after a confirmation; the app process keeps its network guard.
- App log: `%LOCALAPPDATA%\SmartBuildingTranslator\logs\app.log` — counts and error types only.

## 4. Known limitations

- Online mode is shown but disabled (not implemented, by design).
- One translation at a time; the Review screen holds the last translation of this session only.
- Not yet a single `.exe` (Phase 6). Needs the WebView2 Runtime, which Windows 11 includes.
