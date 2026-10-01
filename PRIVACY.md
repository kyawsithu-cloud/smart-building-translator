# Privacy

## Modes
**OFFLINE (default)**
```
Document → this computer → local model (llama-server on 127.0.0.1) → translated document
```
- In offline mode the process installs a `NetworkGuard` that refuses every non-loopback connection.
  If any code path tries to reach the internet, the job fails loudly instead of leaking.
- Only engines declaring `is_local = True` can be selected.

**ONLINE (optional, not implemented in v1)**
```
Document → this app → configured provider (host shown to you) → translated result
```
- Disabled by default. Requires enabling in settings **and** a confirmation dialog per job naming the provider host.
- Never used as an automatic fallback when offline translation fails.
- API keys come from environment variables or the Windows Credential Manager — never source code or plain config.

## Data stored locally (`%LOCALAPPDATA%\SmartBuildingTranslator`)
| Data | Contains document text? | Delete |
|---|---|---|
| Terminology DB | Your glossary only | Settings → Terminology |
| Translation cache / memory | **Yes** (source/target segments) | Settings → Clear history (also can be disabled) |
| Job history | File names, counts, warnings — no text | Settings → Clear history |
| Logs | **No document text** — counts, timings, error types only | Settings → Clear logs |

## Other guarantees
- No telemetry, analytics, crash upload or update check without asking.
- Model downloads happen only when you click Download, from the listed source, with SHA-256 verification.
- Optional encryption at rest (DPAPI-protected key) for the cache DB — planned, not v1.
