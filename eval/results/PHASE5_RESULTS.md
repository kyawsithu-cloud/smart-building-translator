# Phase 5 Results: Quality Control

Date: 2026-10-03 · Hardware: Ryzen 7 5700X, 32 GB RAM, RTX 4060 8 GB · Mode: offline. All documents are the public
test documents in `eval/testset`; translations are the outputs of Phases 1–3 (Hy-MT2-7B, Qwen3-8B,
CAT-Translate-7B). Reproduce: `python scripts/qc_eval.py` (needs PowerPoint for the overflow part).

## 1. What was built

An independent quality checker (`src/sbt/quality/`) that looks at the **finished** translation — after retries,
repair and the user's own corrections — and at the **written file**, not at the translation pipeline's own
bookkeeping. It runs after every translation and after Review edits, and can check a translation made elsewhere.

| Spec item | Checks |
|---|---|
| **Terminology consistency** | approved glossary term not used; a recurring term worded differently across the document (e.g. ビル管理システム on slide 1, 建物管理システム on slide 8), with a one-click "use this wording everywhere"; the same text translated differently in different places |
| **Missing translations** | paragraph not translated; words left in the original language; part missing (much shorter than the document's usual ratio, stops mid-sentence, ends on "and"/、); paragraph **not in the written file** (the file is read back: PowerPoint by paragraph, SmartArt drawings, PDF by the paragraph's area of the page); original text still visible (PDF); pictures with text |
| **Overflow detection** | text exceeding its box (estimated like PowerPoint lays it out); box that grows; title now wrapping onto more lines; font reduced; mixed formatting simplified; fonts not installed / characters a font cannot show / substitute fonts (PDF) |
| **Protected token checking** | identifier changed (192.168.1.100 → 192.168.1.10), missing, or added; numbers and units (counted: one of two °C turned into °F is found; units written out in the target language such as 兆瓦时 = MWh are accepted) |
| **Translation comparison** | Review shows original and translated **pages side by side** with the flagged paragraphs outlined (PDF pages drawn offline; slides drawn by the installed PowerPoint); **Check a translation** compares any original + translated file (from a colleague, an agency, another tool) with the same checks, read-only, exportable as CSV; command line `python -m sbt check original.pptx translated.pptx` |

Results appear on the result screen as four rows (Terminology · Missing or partial · Identifiers and numbers ·
Layout and fonts); a row opens Review filtered to that kind of check. `.report.json` gets a `quality` section
(counts and messages, no document text); the review sheet gets a `checks` column.

## 2. Does each check find what it should? (errors injected into correct translations)

Known errors were injected one at a time into correct translations (Phase 2 + 3 outputs, 9 languages pairs,
PowerPoint and PDF incl. scanned PDFs). "Intended check": the check made for that error reported it on that
paragraph. "Any check": the paragraph was flagged at all, which is what matters to the reviewer. Paragraphs
already flagged before the injection are not counted.

| Injected error | Injected | Found by the intended check | Paragraph flagged by any check |
|---|---|---|---|
| paragraph left untranslated | 126 | 126 (100 %) | 126 (100 %) |
| words left untranslated | 122 | 122 (100 %) | 122 (100 %) |
| number changed | 113 | 113 (100 %) | 113 (100 %) |
| sentence dropped / text cut off | 101 | 60 (59 %) | 96 (95 %) |
| acronym dropped | 96 | 96 (100 %) | 96 (100 %) |
| unit changed | 77 | 76 (99 %) | 76 (99 %) |
| glossary term replaced by another wording | 72 | 72 (100 %) | 72 (100 %) |
| paragraph not written to the file | 63 | 63 (100 %) | 63 (100 %) |
| recurring term worded differently | 56 | 56 (100 %) | 56 (100 %) |
| identifier changed (IP, URL, part number, e-mail) | 43 | 43 (100 %) | 43 (100 %) |
| repeated text translated differently | 10 | 10 (100 %) | 10 (100 %) |
| **all** | **879** | **837 (95 %)** | **873 (99 %)** |

The undetected cases are listed in `phase5/missed.md`.

## 3. False alarms on correct translations

Every warning raised on finished translations was reviewed by hand (`phase5/clean_findings.md`).

| Set | Paragraphs | Warnings | Real problems | Debatable | False alarms |
|---|---|---|---|---|---|
| calibration — Phase 2 + 3 outputs (thresholds were tuned here) | 893 | 12 | 10 | 2 | 0 |
| **held-out** — Phase 1 outputs of three models (not used for tuning) | 863 | 45 | 41 | 2 | **2 (0.2 per 100 paragraphs)** |

Real problems found in earlier outputs, for example: a Chinese character 点 inside Thai text; "Air Handling Unit
(AHU) and Fan Coil Unit (FCU) control" → Thai keeping only "(AHU) and (FCU)"; "Energy Management System (EMS)
for energy consumption analysis" → Japanese dropping the system name; Burmese output "Edge device => …"; and
from CAT-Translate: HVAC → "HVAAC", BMS → "BM", bms.example.com → bmsc.example.com, chat commentary and
repeated "アシスタント" lines inside the translation. Debatable: "firmware", "port" left in English in Burmese.
False alarms: "24/7" → 全天候 (correct, the number is gone) and "AI" → 人工智能 (an acronym translated).

## 4. Overflow: compared with PowerPoint's own layout

PowerPoint (`scripts/measure_text.ps1`, read-only, no window) measured the laid-out text height of every text
box in 64 translated decks (as written, and with some texts made 2–5× longer) — 1,056 text boxes.

| | Overflowing (PowerPoint) | Reported | Missed | False warnings |
|---|---|---|---|---|
| Before Phase 5 | 126 | 32 (25 %) | 94 | 34 |
| **After** | **86** | **74 (86 %)** | **12** | **13** |

What the measurements showed and what was changed:
- Line height is 1.2 × font size in every script, but paragraphs inherit **space before** (0.2 lines) and
  **line spacing** from the slide master, and bullets an **indent**: now read through slide → layout → master.
- A **subtitle** was sized as a title (its type name contains "TITLE"): 44 pt instead of 32 pt. Fixed.
- **Burmese** wraps only at spaces in PowerPoint (the estimate allowed breaks anywhere and predicted half the
  lines).
- Text is now measured with the **font PowerPoint uses** (run typeface or theme font per script, e.g. Meiryo UI,
  Cordia New), not a stand-in.
- 2 pt tolerance (text may run into the inner margin); boxes that already overflowed in the original and boxes
  that grow with their text are reported as information.
Because the estimate is better, the writer also shrinks fonts where needed, so fewer boxes overflow at all
(126 → 86 in the same test). Remaining differences: Thai line breaking (PowerPoint uses a word dictionary) and
titles exactly at a line-break boundary.

## 5. Desktop app

| Check | Result |
|---|---|
| Unit tests | 80 pass (11 new: every check, written-file read-back for PowerPoint and PDF, subtitle size, paragraph spacing, file-pair check, side-by-side pages) |
| Real window: translate the public sample deck | all four quality rows OK; one information note (slide 8 text runs past its box, as in the original); 63 paragraphs verified in the written file |
| Real window: Review → Compare pages | slides drawn by PowerPoint in 3 s; previous/next slide works |
| Real window: check a translation made elsewhere (CAT-Translate output of the same deck) | 63 of 63 paragraphs matched; 6 glossary terms not used, 4 identifier errors (HVAC → HVAAC, BMS → BM, bms.example.com → bmsc.example.com), model commentary and junk lines found; Review read-only |
| JavaScript errors | none |
| Command line `translate` (public spec PDF) | quality summary printed; `.report.json` quality section contains no document text |

## 6. Limitations

- **Meaning errors** that keep all terms, numbers and identifiers (a plausible but wrong sentence) are not
  detected: there is no reference translation offline. Review remains necessary before external use.
- A dropped sentence in a long paragraph is caught by the omission check 59 % of the time (95 % of such
  paragraphs are flagged by some check); short headings are judged leniently because they compress naturally.
- Checking a translation made elsewhere: recurring-term comparison needs the local model (otherwise only glossary
  and repeated-text checks); a PDF that was re-laid out matches paragraphs poorly.
- Slide pictures for the side-by-side view need Microsoft PowerPoint; without it the text comparison remains.
