# Phase 1 Results: Feasibility of Offline EN↔JA PPTX Translation

Date: 2026-09-30 · Hardware: Ryzen 7 5700X, 32 GB RAM, RTX 4060 8 GB · Mode: **offline** (network guard on,
llama-server `--offline`, bound to 127.0.0.1)

**Question:** can we produce good enough English↔Japanese technical translation *locally* while preserving
PowerPoint formatting?

**Answer (preliminary):** **Yes, with Hy-MT2-7B.** It meets the agreed thresholds in both directions on the
public test decks, in 20–40 seconds per 9-slide deck. It is not perfect: about 3 "major" errors per ~50
segments remain, so human review is still needed for documents that leave the company. **Your own review of
the review sheets (below) is the real go/no-go gate.** My review is not a native speaker's.

## 1. Scorecard (automatic)

| Model | Direction | Protected tokens | Glossary | Formatting tags | Warnings | Time | Speed |
|---|---|---|---|---|---|---|---|
| **Hy-MT2-7B** | EN→JA | 100 % | 97.6 % ⚠ | 100 % | 2 | 38 s | 33 tok/s |
| **Hy-MT2-7B** | JA→EN | 100 % | 100 % | 100 % | 3 | 20 s | 32 tok/s |
| Qwen3-8B | EN→JA | 100 % | 100 % | 100 % | 1 | 57 s | 39 tok/s |
| Qwen3-8B | JA→EN | 100 % | 100 % | 100 % | 2 | 48 s | 38 tok/s |
| CAT-Translate-7B | EN→JA | **89.7 %** ✗ | 83.3 % ✗ | 100 % | 13 | 47 s | 44 tok/s |
| CAT-Translate-7B | JA→EN | **93.9 %** ✗ | 100 % | 100 % | 9 | 62 s | 44 tok/s |

All runs: 100 % of segments translated, 0 unflagged failures. "Warnings" includes informational font reductions.
Hy-MT2 EN→JA misses the 98 % glossary target by one segment (see error #2 below). The miss is **flagged** in the
report, not silent.

## 2. Human-style review (MQM-lite, by Claude, not a native speaker)

Every non-trivial segment of each run was read (≈48 per direction).

| Model | Direction | Critical | Major | Minor | Meets "0 critical, ≤5 major"? |
|---|---|---|---|---|---|
| Hy-MT2-7B | EN→JA | 0 | 3 | 4 | Yes |
| Hy-MT2-7B | JA→EN | 0 | 3 | 3 | Yes |
| Qwen3-8B | EN→JA | 0 | 3 | 6 | Yes |
| Qwen3-8B | JA→EN | 0 | 2 | 8 (Title Case everywhere) | Yes |
| CAT-Translate-7B | both | **identifier corruption** (see below) | – | – | **No** |

**Hy-MT2 major errors:**
1. EN→JA: "VAV terminal" → 「端子」 (an electrical terminal). Should be ターミナル/ターミナルユニット.
2. EN→JA: "Energy Management System (EMS) for energy consumption analysis" → 「エネルギー消費量分析用（EMS）」
   omits the system name. Flagged `term_missing` after three attempts.
3. EN→JA: "not acknowledged" → 「対応されない」 (not handled). In BMS usage, alarm *acknowledgement* is a specific
   operator action.
4. JA→EN: 「確認されない」 → "not resolved" (should be "not acknowledged"). Same concept.
5. JA→EN: 「保守チームに…通知して作業指示を作成」 → "…notification to the maintenance team **to create** a work
   order". This changes who creates the work order.
6. JA→EN: 「2025年夏にピーク需要を18%削減」 → "Reduce … **by** the summer of 2025". This turns a result into a
   target. The Japanese fragment is genuinely ambiguous.

**Qwen3 characteristic problems:** 「昇格されます」 for "escalated" (a wrong word choice), blinds → 「カーテン」,
「毎3か月」, half-width colons in Japanese, Title Case on every English bullet. It also **invents formatting tags**;
the pipeline now strips them. Its Japanese reads less natural than Hy-MT2's, and it is ~1.5–2× slower.

**CAT-Translate: rejected.** It altered identifiers: HVAC → "HVAAC", BMS → "BM",
`bms.example.com` → `bmsc.example.com`. The checks caught every case, but a model that silently changes URLs is
unsafe for technical documents. It also cannot take a glossary.

## 3. Other languages (smoke test, EN→X, Hy-MT2 vs Qwen3)

| Target | Hy-MT2 | Qwen3 |
|---|---|---|
| Chinese | 100 % translated, tokens 100 % | tokens 97.4 % |
| Korean | clean | clean |
| Thai | 1 stray Chinese character (「ค่าตั้ง点」), flagged | clean |
| **Burmese** | 96.8 %: 2 short lines came back empty (flagged); rest looks plausible | **poor**: 5 empty, clear mistranslations (Q2 → "until December") |

No glossary exists yet for these pairs, and I cannot judge their quality properly. **Burmese needs your review.**

## 4. Formatting (checked by rendering with the installed PowerPoint)

Preserved: bold/italic/colour on the correct words (including after Japanese word reordering), bullet levels,
tables, grouped shapes, speaker notes, positions and sizes. See `phase1/render/compare_*.png`.

Fixed during the run:
- 「24 ° C」 rendered wide → now 「24℃」 for CJK output.
- Faint Japanese in diagram boxes (the template has no Japanese font) → Meiryo UI is used only when the deck's
  theme defines no East Asian font.

Remaining: single-character line wraps (「クラウドプラットフォー／ム」), and titles shrunk to 85 % look
smaller than neighbouring titles. Windows paths show ¥ instead of \ in Japanese fonts; this is standard Japanese
font behaviour and the character itself is unchanged.

## 5. What the pipeline changes fixed (measured)

| Problem found in run 1 | Fix | Result |
|---|---|---|
| Korean 「들」 inside Japanese | foreign-script check + retry | fixed |
| 冷凍機 → "refrigerators", 占有率, missing "work order" | glossary entries (marked DRAFT) | fixed |
| 第1フェーズ / フェーズ3, Q4 / 第2四半期 inconsistency | slide's earlier lines passed as context | fixed |
| Full names collapsed to acronyms (「AHUおよびFCU」) | current line removed from its own context | fixed |
| Hints ignored on some lines | retry by substituting approved terms into the source | mostly fixed (1 left) |
| Parentheses dropped around acronyms | deterministic repair (asking the model made it worse) | fixed |
| Formatting lost when the model broke tags | re-apply tags from glossary/identifiers | fixed |
| Run-to-run variation | greedy decoding (temperature 0) | output now repeatable |

## 6. Privacy verification

- Network guard: unit-tested; blocks any non-loopback connection from the app process.
- llama-server logs contain only timings and token counts. Searched for test phrases, IPs and URLs: 0 hits.
- Reports (`*.report.json`) contain no document text. The review sheets (`*.review.csv`) do; they are written
  only next to the output file.

## 7. Recommendation

1. **Primary engine: Hy-MT2-7B** (Apache-2.0, all 9 languages, best Japanese, fastest).
2. Keep Qwen3-8B installed as an alternative engine to test on your real documents. Do not use it for Burmese.
3. Remove CAT-Translate (frees 5 GB).
4. **Phase 2 priorities** from these results:
   - Document-level term sheet (translate recurring non-glossary terms once, then lock them).
   - Glossary review UI (all new entries are DRAFT).
   - Optional second-engine repair for flagged segments.

## 8. Your action items

1. Open `phase1/hy-mt2-7b/*.review.csv` in Excel, mark errors (see `eval/README.md`), and tell me whether you agree.
2. Review the DRAFT glossary entries in `data/terminology/smart_building_en_ja.csv` (for example 冷凍機 vs チラー).
3. If possible, test with one **real** (confidential) deck. It stays on this computer.
4. If you read Burmese, check `phase1/hy-mt2-7b/sample_en_en-my_verify.review.csv`.
