# Phase 2 Results: Translation Engine

Date: 2026-10-02 · Hardware: Ryzen 7 5700X, 32 GB RAM, RTX 4060 8 GB · Mode: offline · Model: Hy-MT2-7B (Q6_K),
repair: Qwen3-8B (Q5_K_M). All numbers come from the public test decks in `eval/testset` (no real documents).

## 1. What was built

| Requirement | Implementation | Command |
|---|---|---|
| Terminology dictionary (add/edit/delete/import/export, do-not-translate, priority, context) | SQLite glossary; context keywords pick the right entry per slide; priority breaks ties | `python -m sbt glossary …` |
| Context-aware, consistent translation | Document term sheet + **vote** harmonisation (§3) | automatic (`doc_terms`) |
| Translation memory | Exact reuse (re-validated against today's glossary) + similar-sentence examples | automatic; `--no-memory` |
| Language detection | Offline, all 9 languages | `--src auto` (default) |
| Local model + fallback | Qwen3 repairs paragraphs still flagged after retries | `repair_model` |
| Hardware detection, model recommendation | CPU/RAM/GPU/VRAM; measured speeds only | `python -m sbt doctor` |
| Settings, local history, clear history | `config/default.toml` + user `settings.toml`; job history without text | `python -m sbt history [clear]` |
| Privacy of stored data | Database in `%LOCALAPPDATA%`, never in the project folder | see PRIVACY.md |

Tests: 43 unit tests (pipeline tested with a fake engine), `ruff` clean.

## 2. Final scorecard (defaults: doc_terms = vote, repair = Qwen3)

| Deck | Direction | Translated | Identifiers | Glossary | Formatting | Doc terms (consistent) | Repaired | Warnings* | Time |
|---|---|---|---|---|---|---|---|---|---|
| basic | en→ja | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 0 (–) | 1 | 0 | 38.6 s |
| basic | ja→en | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 3 (100.0 %) | 0 | 0 | 20.8 s |
| basic | en→zh | 100.0 % | 100.0 % | – | 100.0 % | 5 (100.0 %) | 0 | 0 | 24.7 s |
| basic | en→ko | 100.0 % | 100.0 % | – | 100.0 % | 5 (100.0 %) | 0 | 0 | 41.6 s |
| basic | en→th | 100.0 % | 100.0 % | – | 100.0 % | 3 (100.0 %) | 1 | 0 | 83.3 s |
| basic | en→my | 96.8 % | 100.0 % | – | 100.0 % | 5 (100.0 %) | 0 | 5 | 195.8 s |
| consistency | en→ja | 100.0 % | 100.0 % | 100.0 % | – | 9 (100.0 %) | 0 | 0 | 29.8 s |
| consistency | ja→en | 100.0 % | 100.0 % | 100.0 % | – | 10 (100.0 %) | 0 | 0 | 16.1 s |
| consistency | en→zh | 100.0 % | 100.0 % | – | – | 8 (100.0 %) | 0 | 0 | 18.6 s |
| consistency | en→ko | 100.0 % | 100.0 % | – | – | 11 (100.0 %) | 0 | 0 | 34.7 s |
| consistency | en→th | 100.0 % | 100.0 % | – | – | 8 (100.0 %) | 0 | 0 | 68.2 s |
| consistency | en→my | 100.0 % | 100.0 % | – | – | 5 (100.0 %) | 0 | 0 | 179.1 s |

Doc terms = recurring non-glossary terms that ended with one consistent translation (consistency, not correctness; see §3).
*Warnings excluding informational font reductions. Burmese: 2 untranslated identifier-only lines + overflow on dense slides.
Time = translation time on the RTX 4060, excluding model loading (~5 s).

Glossary columns are empty for non-Japanese pairs because the glossary is EN↔JA only.

**English ↔ Japanese meets every Phase 1 threshold for the first time:** identifiers 100 %, glossary 100 %
(Phase 1: 97.6 %), formatting 100 %, nothing untranslated. Compared with Phase 1 on the basic deck, EN→JA
changed in exactly one paragraph (the omission Qwen3 repaired, §4); JA→EN changed wording in 3 of 59
paragraphs with equivalent meaning (e.g. "legacy exports" → "older export formats"), most likely from the
smaller context window changing the model's arithmetic slightly.

## 3. Consistency of recurring terms (the main Phase 2 question)

Test: `consistency_en/ja.pptx`, 8 slides where 10 terms that are **not** in the glossary recur 2–5 times
("free cooling", "condenser water", "load shedding", …). Scored with `scripts/consistency_eval.py`, which
lists the acceptable and known-wrong variants per term (my judgement, reviewable in the script).
*Consistent* = share of occurrences using the most common variant; *correct* = share using an acceptable one.

| Strategy | EN→JA consistent | EN→JA correct | JA→EN consistent | JA→EN correct | EN→JA time |
|---|---|---|---|---|---|
| off: each paragraph on its own | 91 % | 47 % | 100 % | 88 % | 20 s |
| hint: translate each term once, then impose it | 100 % | **31 %** | 100 % | **100 %** | 23 s |
| **vote** (default): majority of in-sentence translations, fix deviating paragraphs | 100 % | 50 % | 100 % | 88 % | 30 s |
| vote + **one glossary review** of the 10 terms (`.terms.csv` → import) | **100 %** | **100 %** | – | – | 25 s |

What this shows:
- **Translating a term on its own (hint) works well JA→EN but badly EN→JA.** In isolation Hy-MT2 produced
  凝縮水 (condensate) for "condenser water", 停電順序 (power-outage sequence) for "load shedding" and
  供給空気温度 for "supply air temperature". Imposing those everywhere made correctness *worse* (47 % → 31 %).
  Inside full sentences the same model wrote 給気温度 and 需要制御換気 correctly.
- **Vote** never made correctness worse than off, and made every term consistent. It corrected genuine
  minority deviations (e.g. 傾向ログ → トレンドログ).
- **Some errors are knowledge gaps, not consistency problems.** Hy-MT2 consistently writes 冷却水プラント for
  "chilled water plant" (should be 冷水プラント), 凝縮水 for "condenser water" (should be 冷却水), 自由冷却 for
  "free cooling" (should be フリークーリング) and 負荷切り下げ for "load shedding". No automatic strategy can
  fix those. The glossary does: after correcting 4 of the 10 terms in the generated `.terms.csv` and importing
  it, EN→JA reached 100 % consistent / 100 % correct (JA→EN was not re-tested this way).
- So the intended workflow is: translate → review `.terms.csv` (UNRESOLVED rows first) → import → future
  documents use your terms.

The off/vote/hint runs are kept in `phase2/doc_terms_comparison/`.

## 4. Repair with a second model

Phase 1 left one flagged omission in EN→JA: "Energy Management System (EMS) for energy consumption analysis"
→ 「エネルギー消費量分析用（EMS）」 (the system name was dropped, even after three Hy-MT2 attempts).
Qwen3 re-translated only that paragraph: 「エネルギー管理システム（EMS）は、エネルギー消費量の分析を行うための
システムです。」. The meaning is complete and the glossary term is present (97.6 % → 100 %), but it is a full
sentence where a slide bullet would normally use 体言止め (minor style issue). In Thai, Qwen3 fixed the stray
Chinese character found in Phase 1.

Cost: about 10–15 s, and only when a flagged paragraph exists (Qwen3 is loaded after Hy-MT2 is unloaded, because
an 8 GB GPU cannot hold both). Qwen3 is never used for Burmese (measured poor in Phase 1).

## 5. Translation memory

Same deck translated twice: run 1 took 26.5 s; run 2 reused 32/32 paragraphs and took 6.8 s (mostly model
loading). A memory entry is reused only if it still passes validation with the current glossary (tested: an old
「チラー警報」 is not reused once the glossary says chiller = 冷凍機). The quality effect of similar-sentence
examples was **not measured**: the test decks have no near-duplicate sentences. Real documents are needed for that.

## 6. Other findings and fixes made during Phase 2

| Finding | Fix |
|---|---|
| A normal desktop leaves ~7.2 GB of 8 GB VRAM free, so the model spilled to the CPU and became slower | Hy-MT2 context reduced to 4k tokens (enough: one paragraph per request); now runs fully on the GPU |
| 「210 MWh/year」 → 「每年2.1亿千瓦时」 in Chinese (×1000), only a warning | changed numbers now trigger a retry, then repair; result: 「210 兆瓦时/年」 (correct) |
| Burmese: candidate terms differing only by an optional space split the vote | spaces ignored when comparing CJK/Thai/Burmese terms |
| Failed paragraphs were counted as "identifiers lost", although the original text stays in the file | identifier/glossary checks count translated paragraphs only; failures reported separately |
| Burmese: two lines consisting mostly of identifiers (`BMS server: 192.168.1.100 (VLAN 20)`, a file path) come back empty | unchanged from Phase 1: flagged and left in English. Known limitation |

## 7. Honest limitations after Phase 2
- **EN→JA terminology still depends on the glossary** for domain terms the model doesn't know. Expect to
  review `.terms.csv` for the first documents of each kind.
- The consistency test covers one deck with 10 terms. Real documents may behave differently, so please report
  terms that come out wrong.
- Similar-sentence memory examples are untested for quality (§5).
- Qwen3 repairs can change the style of a bullet (sentence instead of noun phrase).
- Burmese and Thai outputs are much longer than English, so expect overflow warnings and font reduction on dense slides.

## 8. Your action items
1. Run `python -m sbt doctor`, then translate one real deck. Afterwards, open its `.terms.csv`.
2. Review the DRAFT glossary entries (`python -m sbt glossary list` shows a `draft` flag), especially
   chiller = 冷凍機 vs チラー.
3. Consider adding the terms this phase showed Hy-MT2 gets wrong: chilled water ＝ 冷水, condenser water ＝ 冷却水,
   free cooling ＝ フリークーリング, load shedding ＝ 負荷遮断. They are not added automatically, because they are
   your terminology decisions.
4. Tell me when to start Phase 3 (PDF, OCR, tables, images).
