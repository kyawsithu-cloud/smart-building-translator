# Phase 6 Results: Windows App

Date: 2026-10-03 · Windows 11 Pro (10.0.26200) · Python 3.13.5 · PyInstaller 6.22.3 · Inno Setup 6.7.3 ·
Version 1.0.0. Build: `python packaging\build.py` (see DEVELOPMENT.md).

## 1. What was built

| File | Size | What it is |
|---|---|---|
| `SmartBuildingTranslator-1.0.0-Setup.exe` | 118 MB | per-user installer: no administrator rights, Start menu entry, optional desktop icon, uninstaller (asks before deleting glossaries, history and models), checks for the WebView2 Runtime, downloads nothing |
| `SmartBuildingTranslator-1.0.0-portable.zip` | 151 MB | the same app as a folder to unzip anywhere |
| app folder | 317 MB, 294 files | `SmartBuildingTranslator.exe` (desktop app, no console), `sbt.exe` (command line: translate, check, glossary, history, doctor, download), `_internal\` (Python 3.13, libraries, UI, configuration, seed glossary, OCR models), `LICENSE.txt`, `THIRD_PARTY_LICENSES.txt` (39 libraries with licence texts) |
| `SHA256SUMS.txt` | | fingerprints of the installer and the zip |

No Python, no setup.bat, no dependencies to install. The translation engine and models (7–13 GB) are **not**
inside the app: they are downloaded from the Models screen into `%LOCALAPPDATA%\SmartBuildingTranslator\runtime`, or
an existing folder is chosen (*Models → Models folder → Change…*, e.g. this project's `runtime` folder or one
copied from another PC) — nothing has to be downloaded twice.

Changes to make the code work when installed:
- read-only files are found inside the app folder; engine/models in a models folder that can be chosen
  (`runtime_dir` setting, `SBT_RUNTIME_DIR`); the downloader moved into the package (`sbt download`) and runs as
  `sbt.exe download` in its own process, so the app's process keeps its network guard;
- first start without a model: the Translate screen says so and opens Models;
- `settings.toml` saved by Notepad / PowerShell 5 (UTF-8 with byte-order mark) is accepted (found by the
  installer test);
- the app icon (文A), version information in the programs, licence notices generated from the installed packages;
- `--selftest` (and `--selftest-document`) lets the build check the packaged window without a person.

## 2. Verification

Every build (`packaging\build.py`) runs these against the **built programs**, with a throw-away data folder:

| Check | Result |
|---|---|
| Windows Defender scan of the app folder and of the installer | no threats |
| `sbt.exe doctor` | OK |
| Desktop app self-test: window opens, page rendered, JavaScript bridge (32 functions), paths inside the app folder | OK — usable 2.1 s after start |
| Desktop app translates through its own job path (public sample deck, existing models folder): all 8 steps, quality checks, Review, slide pictures from PowerPoint | OK — 63/63 paragraphs, 0 quality findings, output written |
| `sbt.exe translate` public deck (charts, pictures) | OK — 15/15 paragraphs |
| `sbt.exe translate` scanned PDF (OCR models inside the app) | OK |
| `sbt.exe check` (translation made elsewhere) | OK |

Installer test (silent install into a test folder, then silent uninstall):

| Check | Result |
|---|---|
| install without administrator rights | OK (exit 0): programs, uninstaller, Start menu entry, uninstall entry "Smart Building Translator 1.0.0"; no desktop icon unless chosen |
| installed app self-test | OK |
| installed `sbt.exe download --only ocr-th` (8 MB pinned file into a test folder) | downloaded, SHA-256 verified |
| installed app with an existing models folder chosen (settings file saved with byte-order mark) | engine and models found, no download |
| install again over the same folder (update) | OK |
| silent uninstall | programs, uninstall entry and Start menu entry removed; **your data folder unchanged** |

Not automated (needs a person): the interactive uninstall question about deleting data, SmartBuildingTranslator
started from the Start menu, drag & drop from Explorer onto the installed app.

## 3. Tools used for the build

| Tool | Source | Checks |
|---|---|---|
| PyInstaller 6.22.3 (GPL with exception allowing distribution of built programs) | PyPI | Windows Defender: no threats |
| Inno Setup 6.7.3 (free) | GitHub release of jrsoftware/issrc | SHA-256 as published by GitHub ✓, Authenticode signature valid (Pyrsys B.V.) ✓, Windows Defender: no threats ✓; installed for the user only in `runtime\tools\InnoSetup` (not committed) |

## 4. Setup guide (added after the first build)

On first start (or whenever the translation model is missing) the app opens a four-step guide: **Welcome**
(hardware, expected speed) → **Languages** (the languages you work with, and **Usually translate into**:
automatic or a fixed language such as Chinese — preselected for every document, changeable per document and in
Settings) → **Translation model** (download with size, destination, free space and one overall progress bar; or
from a folder / USB stick: *Copy to this PC* with every model file checked against its official SHA-256 while it is
copied and the engine scanned by Windows Defender, or *Use it where it is*; Korean/Thai scanned-page readers and the
repair model as optional extras) → **Ready**. Models → *Setup guide* opens it again. `sbt translate` uses the same
"usually translate into" setting.

| Check | Result |
|---|---|
| Real window, fresh data folder, empty models folder | the guide opens by itself |
| Languages: Chinese ticked, "Usually translate into: Chinese" | saved; shown in Settings |
| Copy from a folder (engine + the real 5.9 GB Hy-MT2 model) | 6.4 GB copied in 13 s, model fingerprint verified, engine virus-scanned |
| Ready → translate the public sample deck | **To** preselected as Chinese; 63/63 paragraphs translated into Chinese with the copied model |
| Unit tests | 92 pass (6 new: usual target language, opened file preselected, folder scan, verified copy, damaged file rejected, one progress bar for several downloads) |

## 5. Limitations

- Not code-signed (no certificate): Windows SmartScreen shows "Windows protected your PC" on first start of the
  installer → *More info → Run anyway*. Compare the file's SHA-256 with `SHA256SUMS.txt` from your own build.
- Windows 10 (1809+) / 11, 64-bit only; needs the Microsoft Edge WebView2 Runtime (part of Windows 11).
- The models are a separate 7–13 GB download (or a copied folder); the installer stays small and offline.
- PyMuPDF is AGPL-3.0: giving the installer to other people means giving them the complete source code too
  (README, Licence).
