# Privacy

## Modes
**OFFLINE (the only mode in this version)**
```
Document → this computer → local model (llama-server on 127.0.0.1, started with --offline) → translated document
```
- At start-up every command installs a `NetworkGuard` that refuses any connection that is not to this computer.
  If any code path tries to reach the internet, the job fails loudly instead of leaking.
- The translation engine binds to 127.0.0.1 only and runs with `--offline` (it cannot download anything).
- Only engines declaring `is_local = True` exist.

**ONLINE (not implemented)**
```
Document → this app → configured provider (host shown to you) → translated result
```
If it is ever added: disabled by default, enabled in settings **and** confirmed per job with the provider host
shown, never used as an automatic fallback, keys from environment variables or Windows Credential Manager.
Setting `mode = "online"` today is rejected with an error.

## What is stored, and where
Everything is local, in `%LOCALAPPDATA%\SmartBuildingTranslator\sbt.db` (SQLite), outside the project folder,
so copying or uploading the project never includes it.

| Data | Contains document text? | How to delete |
|---|---|---|
| Glossaries | Your terms only | `python -m sbt glossary delete <id>`, or delete the database |
| Translation memory | **Yes** (source and translated paragraphs) | `python -m sbt history clear` (also compacts the file so the text is really gone). Turn off with `use_memory = false`, or per job with `--no-memory` |
| Job history | File names, counts, timings; **no** document text | `python -m sbt history clear` |
| Output files | **Yes**: `_JA.pptx`, `.review.csv`, `.terms.csv` next to your document | delete them like any file |
| Logs (`runtime\logs`) | **No**: counts, timings and error types only | delete the folder |

Verified in Phase 1: the engine logs were searched for test phrases, IP addresses and URLs; there were no hits.

## Other guarantees
- No telemetry, analytics, crash upload or update check.
- Model downloads happen only when you run the download script: pinned versions from the official sources,
  SHA-256 checked, program files scanned by Windows Defender.
- Optional encryption at rest (DPAPI-protected key) for the database is planned, not implemented.
