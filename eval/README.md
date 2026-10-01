# Evaluation

Only public, generated content lives here (`testset/` is produced by `scripts/make_test_decks.py`).
Never put real work documents in this folder.

## Automatic metrics (every run, in `*.report.json`)
| Metric | Go threshold (agreed 2026-09-30) |
|---|---|
| protected_token_integrity_pct | 100 |
| glossary_adherence_pct | ≥ 98 |
| tag_integrity_pct (formatting mapped back correctly) | ≥ 95 |
| translated_pct / unflagged untranslated text | 100 / 0 |

## Human review (MQM-lite)
Open `results/phase1/<model>/*.review.csv` in Excel and add two columns: `error_type`, `severity`.

- error_type: terminology · mistranslation · omission · addition · unnatural · register · formatting
- severity: critical (wrong technical meaning, could cause a wrong action) · major (meaning unclear or
  noticeably wrong) · minor (style, awkward but correct)

Go criterion for the chosen model: **0 critical and ≤ 5 major per 50 segments**, per direction.
