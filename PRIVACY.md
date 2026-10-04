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
- OCR (scanned PDFs, pictures) runs locally on the CPU with models stored inside the installed Python package or
  `runtime\ocr`; it never downloads models at run time (that would be blocked by the network guard anyway).
- The desktop app is a window drawn by Microsoft Edge WebView2 (part of Windows 11). Its page is served from
  this folder by a small server on 127.0.0.1 and has a content security policy that blocks every request to
  another address, so the page itself cannot load or send anything over the internet. The window runs in
  private mode (no browser cache, cookies or history are kept). Talking to Python goes through WebView2's
  in-process bridge, not the network.
- Model downloads started from the **Models** screen run in a separate process after you confirm; the app
  process keeps its network guard. Nothing is downloaded automatically.
- Quality checks run on this PC. For the side-by-side page view, PDF pages are drawn by the app; PowerPoint
  slides are drawn by the PowerPoint installed on this PC (opened read-only, without a window; your own open
  presentations are not touched). The pictures are kept in `%LOCALAPPDATA%\SmartBuildingTranslator\cache`
  and deleted when the next job starts, when the app closes, and when it starts again.

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
| Glossaries | Your terms only | Glossary screen, `python -m sbt glossary delete <id>`, or delete the database |
| Translation memory | **Yes** (source and translated paragraphs, including your corrections from Review) | History screen → *Clear history*, or `python -m sbt history clear` (also compacts the file so the text is really gone). Turn off with `use_memory = false`, or per job with `--no-memory` |
| Job history | File names, counts, timings; **no** document text | `python -m sbt history clear` |
| Output files | **Yes**: `_JA.pptx`, `.review.csv`, `.terms.csv` next to your document | delete them like any file |
| Logs (`runtime\logs`, `%LOCALAPPDATA%\SmartBuildingTranslator\logs`) | **No**: counts, timings and error types only | delete the folders |
| Settings (`settings.toml`) | **No** | Settings screen, or delete the file |
| Quality report (`.report.json` → `quality`) | **No**: counts and messages only | with the output files |
| Exported checks (`.checks.csv`) | **Yes**: the paragraphs concerned | delete like any file |
| Page pictures (`cache`) | **Yes** (pictures of pages) | deleted automatically (next job, app closed or started) |

Verified in Phase 1: the engine logs were searched for test phrases, IP addresses and URLs; there were no hits.

## Other guarantees
- No telemetry, analytics, crash upload or update check.
- Model downloads happen only when you click Download (or run `sbt download`): pinned versions from the official
  sources, SHA-256 checked, program files scanned by Windows Defender. Models copied from a folder or USB stick in
  the setup guide get the same checks (fingerprint of every model file, Defender scan of the engine).
- The installer copies files only; it downloads nothing and needs no administrator rights. The installed app has
  the same guarantees as running from source (network guard, page security policy, local data only). Uninstalling
  asks before deleting `%LOCALAPPDATA%\SmartBuildingTranslator` (glossaries, memory, history, models).
- Each build is scanned with Windows Defender and its SHA-256 recorded in `dist\SHA256SUMS.txt`. The programs are
  not code-signed.
- Optional encryption at rest (DPAPI-protected key) for the database is planned, not implemented.
