# Smart Building Translator

Private, offline-first translation of technical documents (PPTX, later PDF) between English and Japanese,
with terminology control and formatting preservation. Domain: smart buildings, BMS/BAS, HVAC, energy, IoT.

**Status: Phase 1 — feasibility POC (command line).** See [ARCHITECTURE.md](ARCHITECTURE.md).

## Translate a deck (already set up on this PC)
**Easiest:** drag a `.pptx` file onto `translate.bat`. The language is detected automatically:
English decks become Japanese, Japanese decks become English.

**From a terminal** (in this folder):
```
.venv\Scripts\python -m sbt.poc translate "C:\path\deck.pptx"                  # auto: en→ja or ja→en
.venv\Scripts\python -m sbt.poc translate "C:\path\deck.pptx" --src en --tgt zh  # other languages
.venv\Scripts\python -m sbt.poc translate "C:\path\deck.pptx" --cpu             # GPU busy (e.g. a game)
```
Results are written **next to the original**, which is never modified:
`deck_JA.pptx`, `deck_JA.review.csv` (side-by-side, open in Excel) and `deck_JA.report.json` (warnings).

Notes:
- `.pptx` only for now. PDF support is Phase 3; save older `.ppt` files as `.pptx` first.
- Close the file in PowerPoint before translating if you want to overwrite a previous `_JA` output.
- Speed: ~20–40 s per 10 slides on the RTX 4060 when the GPU is free; about 5 min on the CPU (`--cpu`).
  Games or other GPU-heavy apps slow it down a lot.
- Languages: en, ja, zh, ko, my, th, de, fr, es (the glossary currently covers en↔ja only).

## Install from GitHub (Windows 11)
1. Install **Python 3.13 (64-bit)** from python.org.
2. Download this repository (green **Code** button → *Download ZIP*, then unzip; or `git clone`).
3. Double-click `setup.bat` (downloads the small Python libraries from PyPI).
4. Download the translation engine and model, about 7 GB, from their official sources, hash-verified:
   ```
   .venv\Scripts\python.exe scripts\download_phase1.py --only llama-cuda cudart hy-mt2-7b
   ```
5. Drag a `.pptx` onto `translate.bat`.

After installation everything runs **offline**. No document content ever leaves the PC.

## Use on another PC
1. Install **Python 3.13 (64-bit)** from python.org on the new PC (keep "py launcher" ticked).
2. Copy this whole folder (~13 GB). You can skip `.venv` and `runtime\downloads`.
   **Do not copy `runtime\cache`**: it holds text from documents you translated.
3. Double-click `setup.bat`. It works offline: the libraries are in `runtime\wheels`.
4. Drag a `.pptx` onto `translate.bat`.

Without an NVIDIA GPU it runs on the CPU (about 5 min per 10 slides). An NVIDIA GPU needs a recent driver
(CUDA 13 support, driver 580 or newer).

## Developer setup (from scratch)
```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
py -3.13 scripts/download_phase1.py                 # runtime + models, hash-verified
.venv\Scripts\python scripts/make_test_decks.py      # public test decks
.venv\Scripts\python -m sbt.poc translate eval\testset\sample_en.pptx --src en --tgt ja --model hy-mt2-7b
.venv\Scripts\python scripts/run_eval.py             # all models, EN→JA and JA→EN, scorecard
```
Output: `name_JA.pptx`, `name_JA.report.json` (metrics and warnings, no document text) and `name_JA.review.csv`
(side-by-side source/translation for review, opens in Excel).

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Requirements analysis, research, options, recommendation, POC plan, evaluation method |
| [PRIVACY.md](PRIVACY.md) | Offline/online modes, what leaves the machine (nothing, by default) |
| [MODEL_SETUP.md](MODEL_SETUP.md) | Local model runtime and model installation |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Dev environment, layout, conventions, how to add a provider |

## Principles
1. Privacy — offline by default; online only by explicit, per-job consent.
2. Technical accuracy — glossary, protected tokens and document-level consistency are enforced in code.
3. Formatting preservation — originals are never modified; output is `name_JA.pptx`.

## Known limitations (planned, honest)
- Local models are below frontier cloud translation quality on long, complex sentences. Review before external use.
- PDF output will be positioned but not pixel-faithful; complex layouts may fall back to bilingual output.
- Text inside images is detected and reported, not translated (until OCR-on-images is added).

## Licence
MIT for this project's code (see `LICENSE`). Models are downloaded separately under their own
licences: Hy-MT2 and Qwen3 are Apache-2.0, llama.cpp is MIT.
