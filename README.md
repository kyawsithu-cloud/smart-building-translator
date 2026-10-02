# Smart Building Translator

Private, offline-first translation of technical documents (PowerPoint and PDF, including scanned PDFs) between
English and Japanese
(plus Chinese, Korean, Burmese, Thai, German, French, Spanish), with terminology control and formatting
preservation. Domain: smart buildings, BMS/BAS, HVAC, energy, IoT.

**Status: Phase 3 — document processing (command line).** Results: [Phase 1](eval/results/PHASE1_RESULTS.md),
[Phase 2](eval/results/PHASE2_RESULTS.md), [Phase 3](eval/results/PHASE3_RESULTS.md).
Design: [ARCHITECTURE.md](ARCHITECTURE.md).

## Translate a document
**Easiest:** drag a `.pptx` or `.pdf` file onto `translate.bat`. The language is detected automatically:
English documents become Japanese, Japanese documents become English, other languages become English.

What is translated:

| | PowerPoint (.pptx) | PDF |
|---|---|---|
| Text boxes, titles, bullets, tables | yes, formatting kept | yes: text replaced in place, fonts/colours/bold kept |
| Speaker notes | yes | – |
| Charts | titles, axis titles, series names, category labels | as page text |
| SmartArt | yes (diagram text and its displayed copy) | as page text |
| Scanned pages | – | yes, read by OCR (offline); check the review sheet |
| Text inside pictures | detected and reported, not translated | detected and reported, not translated |

**From a terminal** (in this folder):
```
.venv\Scripts\python -m sbt translate "C:\path\deck.pptx"                   # auto-detect language
.venv\Scripts\python -m sbt translate "C:\path\deck.pptx" --src en --tgt zh   # choose languages
.venv\Scripts\python -m sbt translate "C:\path\deck.pptx" --cpu              # GPU busy (e.g. a game)
.venv\Scripts\python -m sbt translate "C:\path\deck.pptx" --no-memory        # don't store this document
.venv\Scripts\python -m sbt translate "C:\path\spec.pdf" --no-ocr            # skip scanned pages / picture text
```
Results are written **next to the original**, which is never modified:

| File | Contents |
|---|---|
| `deck_JA.pptx` | the translated copy |
| `deck_JA.review.csv` | source and translation side by side (Excel) |
| `deck_JA.terms.csv` | recurring terms found in the deck and how they were translated, in glossary format |
| `deck_JA.report.json` | checks and warnings (no document text) |

## How translation quality is controlled
1. **Glossary**: your approved terms are always used (checked; retried if the model ignores them).
2. **Document term sheet**: terms that recur in the deck but aren't in the glossary are kept consistent: the
   translation the model uses most often wins, and deviating paragraphs are re-translated.
3. **Translation memory**: paragraphs translated before are reused (if still valid with today's glossary),
   and similar earlier sentences are shown to the model as examples.
4. **Repair**: paragraphs still flagged after retries are re-translated by a second model (Qwen3).
5. **Checks**: identifiers (URLs, IPs, part numbers, acronyms), numbers, formatting, untranslated text,
   text overflow.

### Improving terminology (recommended after each new type of document)
1. Open `deck_JA.terms.csv` in Excel. Fix wrong translations (rows marked UNRESOLVED need a decision).
2. Import it: `.venv\Scripts\python -m sbt glossary import "C:\path\deck_JA.terms.csv"`
3. From now on those terms are translated your way in every document.

On the Phase 2 test deck, one review of 10 terms raised correct terminology from 47 % to 100 %.

## Other commands
```
python -m sbt glossary list [search]          # view terms (id, languages, flags, context)
python -m sbt glossary add "supply air temperature" "給気温度"
python -m sbt glossary add "BACnet" --dnt      # do not translate
python -m sbt glossary add "alarm" "アラーム" --context "screen,display"   # used only on slides mentioning these
python -m sbt glossary edit 12 --target "冷水プラント" --priority high
python -m sbt glossary delete 12
python -m sbt glossary export terms.csv       # edit in Excel, then `glossary import terms.csv`
python -m sbt history                         # recent jobs
python -m sbt history clear                   # delete job history and stored translations
python -m sbt doctor                          # hardware check, installed models, recommendation
```
(Prefix with `.venv\Scripts\` when running from this folder.)

Your glossary, translation memory and job history are stored on this PC in
`%LOCALAPPDATA%\SmartBuildingTranslator` (not in the project folder), so copying or uploading the project never
includes document content. Optional settings go in `%LOCALAPPDATA%\SmartBuildingTranslator\settings.toml`
(see `config/default.toml` for the keys).

## Install from GitHub (Windows 11)
1. Install **Python 3.13 (64-bit)** from python.org.
2. Download this repository (green **Code** button → *Download ZIP*, then unzip; or `git clone`).
3. Double-click `setup.bat` (downloads the small Python libraries from PyPI).
4. Download the translation engine and model (about 7 GB) from their official sources, hash-verified:
   ```
   .venv\Scripts\python.exe scripts\download_phase1.py --only llama-cuda cudart hy-mt2-7b
   ```
   Optional, for repair of flagged paragraphs (+5.6 GB): `... --only qwen3-8b`
5. Run `.venv\Scripts\python -m sbt doctor`, then drag a `.pptx` onto `translate.bat`.

After installation everything runs **offline**. No document content ever leaves the PC.

## Use on another PC
1. Install **Python 3.13 (64-bit)** on the new PC (keep "py launcher" ticked).
2. Copy this whole folder (~13 GB). You can skip `.venv` and `runtime\downloads`.
3. Double-click `setup.bat`. It works offline: the libraries are in `runtime\wheels`.
4. To take your glossary along: `python -m sbt glossary export my_terms.csv` on the old PC,
   `python -m sbt glossary import my_terms.csv` on the new one.

Without an NVIDIA GPU it runs on the CPU (about 5 min per 10 slides). An NVIDIA GPU needs a recent driver
(CUDA 13 support, driver 580 or newer).

## Developer setup
```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
py -3.13 scripts/download_phase1.py                 # runtime + models, hash-verified
.venv\Scripts\python scripts/make_test_decks.py      # public test decks
.venv\Scripts\python -m pytest                       # unit tests (no model needed)
.venv\Scripts\python scripts/run_eval.py --models hy-mt2-7b --repair qwen3-8b   # scorecard
.venv\Scripts\python scripts/consistency_eval.py eval/results/phase2/hy-mt2-7b  # term consistency
```

| Doc | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Requirements analysis, research, options, recommendation, evaluation method |
| [PRIVACY.md](PRIVACY.md) | Offline mode, what is stored where, how to delete it |
| [MODEL_SETUP.md](MODEL_SETUP.md) | Translation engine and model installation |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Layout, conventions, how to add a model or provider |

## Principles
1. Privacy: offline by default; online only by explicit, per-job consent (not implemented).
2. Technical accuracy: glossary, protected identifiers and document-level consistency are enforced in code.
3. Formatting preservation: originals are never modified; output is `name_JA.pptx`.

## Known limitations
- Local models are below frontier cloud translation quality on long, complex sentences, and they make
  domain-term mistakes (e.g. condenser water → 凝縮水) until the glossary covers those terms. Review before
  external use.
- PDF output keeps the layout but is not pixel-identical: text that needs more room is placed in the free space
  to its right/below or shrunk (reported). Very dense layouts, rotated text and text in vector drawings are
  harder; rotated text is kept as-is and reported.
- Scanned PDFs: OCR reads English/Japanese/Chinese/Latin languages (Korean and Thai need the optional models in
  MODEL_SETUP.md; there is no Burmese OCR). OCR'd text loses bold, and colour only where the scan is in colour.
- Text inside pictures is detected and reported, not translated. A chart's data sheet (Edit Data) keeps the
  original labels.
- `.ppt`, Word and Excel files are not supported (save as .pptx/.pdf). Command line only; the UI is Phase 4.

## Licence
MIT for this project's code (see `LICENSE`). Models are downloaded separately under their own
licences: Hy-MT2 and Qwen3 are Apache-2.0, llama.cpp is MIT, RapidOCR and its PaddleOCR models are Apache-2.0.

**PDF support uses PyMuPDF, which is AGPL-3.0.** For private or open-source use this changes nothing. If you ever
distribute a packaged build (e.g. an `.exe`) to others, the AGPL applies to that build: its complete source must
be available (it already is, on GitHub) — or a commercial PyMuPDF licence is needed for closed distribution.
