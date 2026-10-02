# Phase 3 Results: Document Processing

Date: 2026-10-02 · Hardware: Ryzen 7 5700X, 32 GB RAM, RTX 4060 8 GB · Mode: offline · Translation: Hy-MT2-7B,
repair: Qwen3-8B · OCR: RapidOCR (PP-OCRv6 multilingual, CPU). All test files are public/generated
(`eval/testset`); three SmartArt/chart samples are Apache POI test files (`eval/testset/external`, Apache-2.0).

## 1. What was built

| Format / element | How | Status |
|---|---|---|
| **PDF (text)** | Paragraphs rebuilt from lines across blocks; bullets/numbering kept as prefixes; bold/italic/colour as tags → CSS; tables via PyMuPDF's table detector (cell = paragraph) | done |
| **PDF output** | Original text removed by redaction (images and vector graphics untouched); translation laid out in the original box, growing into free space right/below, shrinking only if needed; Windows fonts per language, subset-embedded | done |
| **Scanned PDF** | Image-only pages detected → OCR (offline) → lines grouped into paragraphs (bullets, table rules, column borders respected) → original lines covered with their background colour → translation drawn on top | done |
| **PPTX charts** | Chart title, axis titles, series names, category labels | done (data sheet keeps original labels — reported) |
| **PPTX SmartArt** | Diagram text **and** the cached drawing PowerPoint displays | done |
| **Text in pictures** | OCR detects text in pictures (PPTX and PDF) → reported per slide/page | detected, not translated |
| **Errors** | Clear messages for password-protected PDFs, broken/unsupported files; damaged PDFs that can be repaired are processed **with a warning** | done |

60 unit tests (incl. PDF parse/render, OCR, charts, SmartArt, error files); `ruff` clean.

## 2. Scorecard (defaults: doc_terms = vote, repair = Qwen3)

| File | Direction | Translated | Identifiers | Glossary | Formatting | Real warnings | Repaired | OCR paragraphs | Time |
|---|---|---|---|---|---|---|---|---|---|
| sample_en.pptx | EN→JA | 100 % | 100 % | 100 % | 100 % | 0 | 1 | – | 39 s |
| sample_ja.pptx | JA→EN | 100 % | 100 % | 100 % | 100 % | 0 | 0 | – | 21 s |
| rich_en.pptx (chart + pictures) | EN→JA | 100 % | n/a | 100 % | n/a | 0 | 0 | – | 5 s |
| rich_ja.pptx | JA→EN | 100 % | n/a | 100 % | n/a | 0 | 0 | – | 4 s |
| spec_en.pdf (2-page spec) | EN→JA | 100 % | 100 % | 100 % | 100 % | 0 | 0 | – | 26 s |
| spec_ja.pdf | JA→EN | 100 % | 100 % | 100 % | 100 % | 0 | 2 | – | 18 s |
| slides_en.pdf (PowerPoint export) | EN→JA | 100 % | 100 % | 100 % | 100 % | 3 overflow | 1 | – | 44 s |
| spec_en_scanned.pdf | EN→JA | 100 % | 100 % | 100 % | n/a | 0 | 0 | 29 | 27 s |
| spec_ja_scanned.pdf | JA→EN | 100 % | 100 % | 100 % | n/a | 0 | 0 | 29 | 15 s |

"Real warnings" excludes informational font reductions. The 3 overflow warnings on the slide PDF are dense
diagram labels and table cells where Japanese needed to shrink below 80 % (still readable, flagged).
Visual comparisons: `phase3/render/*.png`.

## 3. OCR accuracy (scripts/ocr_eval.py)

Character error rate (CER) of OCR against the known text of the original PDF, each reference line paired with
its closest OCR line.

| Scanned page | Single pass | Pipeline (re-read + clean-up) | Pipeline, notation ignored* | Time |
|---|---|---|---|---|
| English p1 | 0.12 % | 0.12 % | **0.00 %** | 2.3 s |
| English p2 | 0.69 % | 0.69 % | **0.69 %** | 1.1 s |
| Japanese p1 | 5.41 % | 5.20 % | **0.42 %** | 1.9 s |
| Japanese p2 | 6.01 % | 6.01 % | **0.55 %** | 1.1 s |

\* Full-/half-width forms (（）/(), ％/%, ～/~), dash and bullet variants — same meaning for the reader and the
translator. Remaining real errors: — read as ー, ウェイ as ウエイ, one missing °.
Test scans are clean 200-dpi greyscale renders with added noise; **real scanner/camera images will be worse**.

## 4. Problems found by testing, and the fixes (measured)

| Found | Effect | Fix |
|---|---|---|
| Exported slide PDFs put each line in its own block | "…(FCU)" and "control" translated separately | paragraphs rebuilt across blocks |
| Side-by-side labels on one baseline | 4 diagram labels became one paragraph | lines split at large gaps |
| Hyphen extracted as U+00AD / U+2012 | identifier `FX-PCG2611-0` not recognised | hyphen look-alikes normalised |
| Several headings per PDF page given as context | Hy-MT2 **added the next heading** to a translation | context = nearest heading only; extra lines → retry |
| Model emitted CJK *compatibility* ideographs (年 as U+F98E) | Japanese left in English output, shown as □, not detected | normalised; any wide character in Latin output = untranslated → retry/repair |
| URL pattern ran into following Japanese text | false "identifier changed" | URL/path patterns stop at non-URL characters; host names protected |
| Translated text squeezed into the tight English box | Japanese shrunk to 46–78 % | text may use free space to the right/below |
| OCR orientation classifier | flipped upright lines into garbage (EN line read as "clo s d t s r…", Korean line as "\|") | classifier off (pages are rendered upright); low-confidence lines re-read from a padded crop |
| OCR line grouping | bullets and table rows merged into one paragraph | split at bullets, drawn rules and column borders |
| Kanji/katakana look-alikes, simplified/old forms | 工スカレー, 設定值, 溫度 | Japanese OCR clean-up (only characters that cannot be correct) |
| Red note under black text | merged into one paragraph, formatting simplified | a colour change starts a new paragraph |
| Spaces between Japanese words after term-injection retries | 「システム は 消費量 の」 | spaces between Japanese characters removed |

## 5. Limitations (honest)
- **PDF output is faithful in layout but not pixel-identical.** Text needing more room uses nearby free space or
  shrinks (reported). Dense layouts, multi-column magazines, rotated text (kept, reported) and text that is part
  of vector drawings are the hardest cases. Tested on 4 PDF layouts only.
- **Scanned pages**: OCR'd text loses bold/italic; colour only if the scan is in colour; text sizes are estimated.
  Burmese has no OCR model. Real-world scans (skewed, low resolution, stamps, handwriting) were not tested.
- **Text in pictures** is detected and reported, not translated.
- **Model errors remain** (unchanged from Phase 2): e.g. "VAV terminal" → 端子, "Commissioning Photos" → 撮影写真.
  The glossary is the fix.
- **SmartArt** was tested on one public sample (simple process diagram); complex SmartArt layouts may display the
  cached drawing differently.

## 6. Your action items
1. Try one real PDF (text-based) and one scanned PDF from work: `python -m sbt translate file.pdf`.
   Check the `.review.csv` for the OCR'd paragraphs.
2. If you use Korean/Thai scans: the OCR models are installed (`runtime\ocr`).
3. Licence decision only if you plan to distribute an `.exe` to others: PyMuPDF is AGPL (see README).
4. Tell me when to start Phase 4 (desktop UI: drag & drop, progress, review/edit screen, glossary editor).
