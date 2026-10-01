# Smart Building Translator — Architecture & Feasibility Analysis

Status: **Proposal (pre-Phase 1)**. Nothing here is final until the Phase 1 POC has produced measured results.
Research snapshot date: 2026-09-30. Model landscape changes monthly — re-verify versions and licenses before locking choices.

Priorities, in order: **Privacy → Technical translation accuracy → Formatting preservation**. Speed is explicitly secondary.

---

## 1. Requirements analysis

### 1.1 What the product actually is
A **document-to-document** translation pipeline, not a text translator. The core value is in three places:

1. **Structure round-tripping** — PPTX/PDF → an intermediate model of text segments with formatting and position → translated → written back into a *copy* of the original.
2. **Terminology control** — glossary, do-not-translate list, protected tokens, document-level consistency.
3. **Honest quality reporting** — the app must know (and say) what it could not translate, what overflowed, and what it is unsure about.

### 1.2 Requirement classification

| Area | Must have (v1) | Later |
|---|---|---|
| Privacy | Offline by default, no telemetry, loopback-only inference, no content in logs, explicit online consent | Encrypted local storage |
| Formats | PPTX (text boxes, placeholders, groups, tables, notes) | PDF text-layer, scanned PDF/OCR, charts, SmartArt, text in images |
| Translation | EN↔JA, glossary, protected tokens, document-level context, cache | Other languages, translation memory with fuzzy match, model A/B |
| QA | Protected-token check, missing translation, term consistency, overflow estimate | Rendered visual diff |
| UI | Upload, languages, mode, progress, report, open file/folder | Side-by-side review/edit, model manager, dark/light |
| Packaging | Dev environment | Single Windows installer, bundled runtime and model downloader |

---

## 2. Technically difficult parts (ranked by risk)

1. **EN→JA quality on a local model.** Japanese output quality is the harder direction. Slides are mostly *fragments* ("Energy saving control", "Peak demand"), which carry little context and force the model to guess. This is the #1 feasibility question and the reason for Phase 1.
2. **Mapping translated text back onto formatting runs.** A paragraph like "The **BMS** monitors *HVAC* equipment" has 5 runs. Japanese reorders words, so runs cannot be mapped 1:1 by position. Plan: wrap runs in inline tags (`<r1>BMS</r1>`), require the model to keep the tags, validate, and fall back to "dominant formatting for the whole paragraph + warning" if the tags are broken. Small translation-specialised models may not keep tags reliably. **This must be measured in the POC.**
3. **Text expansion/contraction and overflow.** PowerPoint does not tell you the rendered size of text; python-pptx has no layout engine. We must estimate text extents ourselves from font metrics (fontTools/Pillow with the real font file), respecting autofit settings, insets, and line wrapping rules for Japanese (no spaces; kinsoku rules). Estimates will be approximate. An optional LibreOffice headless render can be used later for visual checks.
4. **PDF reconstruction.** PDFs have no "text box" concept — only positioned glyphs. Rebuilding a translated PDF means: find text blocks, remove the original text (redaction), insert translated text into the same rectangle with a Japanese-capable font, and shrink to fit. It works well for simple layouts and degrades on dense, multi-column or vector-heavy engineering drawings. Expect PDF output to be "readable and positioned", not pixel-faithful.
5. **Scanned PDFs / OCR.** Japanese OCR on low-resolution scans is error-prone; translating OCR errors multiplies them. OCR output must be flagged as lower confidence in the report.
6. **Document-level consistency** without sending the whole deck in one prompt (context-window and VRAM limits on an 8 GB GPU).
7. **Packaging** Python + CUDA inference + model files into a single installer without requiring the user to install Python.

---

## 3. Local translation options — research summary

### 3.1 Categories

| Category | Examples | Strength | Weakness for this project |
|---|---|---|---|
| Classic NMT (seq2seq) | NLLB-200, M2M100, MarianMT/Opus-MT, Argos Translate | Fast, small, CPU-friendly | Sentence-level only; no glossary conditioning; weak EN↔JA technical quality (Opus-MT en-jap is known-poor); **NLLB is CC-BY-NC** (non-commercial) |
| Translation-specialised LLMs | **TranslateGemma** (4B/12B/27B, Google, 2026), **Hy-MT 1.5 / Hy-MT2** (Tencent, 1.8B/7B), **CAT-Translate** (CyberAgent, 0.8–7B, JA↔EN only), **PLaMo 2 Translate** (PFN) | Best quality per parameter for plain translation; some support terminology & context prompts natively (Hy-MT) | Narrower instruction-following: may not keep inline tags / JSON batches; languages vary |
| General instruction LLMs | **Qwen3** (4B/8B/14B/32B, Apache-2.0), **Gemma 3** (4B/12B/27B), Llama 3.x, Japanese-tuned (Swallow, ELYZA, llm-jp) | Follow complex instructions: glossary, tags, JSON output, style rules, context | Slightly lower raw translation quality than specialised models at the same size; can "explain" instead of translate if not constrained |

### 3.2 Shortlist for the Phase 1 bake-off (fits an RTX 4060 8 GB)

| Candidate | Why | Licence notes (verify!) | Est. Q4 GGUF size |
|---|---|---|---|
| **Qwen3-8B** | Best candidate for the *structured* job: tags, JSON, glossary rules. Strong JA/ZH. | Apache-2.0 — clean | ~5 GB |
| **TranslateGemma 12B** (and 4B as low-end option) | Modern translation-specialised model, 55 languages | Gemma Terms of Use | ~7–7.5 GB (tight on 8 GB; partial CPU offload likely) |
| **Hy-MT 1.5 7B / Hy-MT2 7B** | Built-in *terminology intervention* and *contextual translation* prompts; official GGUF | Tencent Hunyuan community licence — historically has territorial and scale restrictions; **must read before use** | ~4.5–5 GB |
| **CAT-Translate 7B / 3.3B** | JA↔EN specialist, evaluated on business/legal/patent domains | MIT — clean | ~4.5 GB / ~2 GB |

**Update after verification (2026-09-30):**
- **Hy-MT2-7B** (released May 2026) is **Apache-2.0** with official GGUF builds, supports all 9 target languages
  (EN, JA, ZH, KO, MY, TH, DE, FR, ES), and documents terminology, background-context and delimiter prompts.
  It is the primary candidate.
- **TranslateGemma** is gated behind accepting Google's Gemma terms on Hugging Face; deferred until you decide to
  accept them. CyberAgent's published benchmarks also show CAT-Translate-7B ahead of it on EN↔JA.
- Phase 1 models actually installed: Hy-MT2-7B Q6_K, Qwen3-8B Q5_K_M, CAT-Translate-7B Q5_K_M.

**Language coverage plan:** EN↔JA is the measured, primary pair. Hy-MT2 and Qwen3 also cover ZH/KO/MY/TH/DE/FR/ES;
the pipeline, glossary (bidirectional) and renderer are language-agnostic, so other pairs work with the same
code. Their quality is smoke-tested in Phase 1 but not formally scored until you (or a reviewer) can judge them.

**Excluded or deprioritised**
- **PLaMo 2 Translate** — strong JA↔EN, but the PLaMo Community Licence only permits use by companies/individuals under ¥1 billion annual revenue. Larger organisations are therefore **not licensed** to use it. Excluded unless you confirm otherwise.
- **NLLB-200** — non-commercial licence and weak EN↔JA technical quality.
- **Opus-MT / Argos** — quality too low for EN↔JA technical text; kept only as a possible ultra-light fallback for other language pairs.
- **27B–32B models** — likely better quality, but on 8 GB VRAM they run mostly on CPU (slow). Worth one measured run in the POC as an "upper bound" reference, not as the default.

### 3.3 Likely final engine design: two roles, switchable
The POC may show that the best *translator* is not the best *instruction follower*. The architecture therefore allows:
- **Translator model** — translates segments (with glossary hints).
- **Structure/QA model** (optional, may be the same model) — repairs broken tags, extracts candidate terms, checks consistency.

Each is a `TranslationEngine` implementation selected in config; the pipeline does not care which model is behind it.

### 3.4 Inference runtime

| Option | Verdict |
|---|---|
| **llama.cpp `llama-server`** (bundled .exe, CUDA build) | **Recommended for the app.** Single binary, GGUF models, CUDA/Vulkan/CPU, JSON-schema/GBNF constrained output, OpenAI-compatible API, we control the bind address (127.0.0.1) and lifecycle. No separate install for the user. |
| Ollama | **Good for development** (easy model pulls). Runs as a separate background service with its own model store; less control over packaging. Supported as an alternative adapter. |
| Hugging Face Transformers / CTranslate2 | Needed only if we use a non-GGUF model (e.g. NMT). Heavier dependency (PyTorch/CUDA ~2–3 GB). Not in v1. |
| LLamaSharp (.NET) | Viable if the core were C#; not chosen (see §5). |

---

## 4. Document processing options — research summary

### 4.1 PPTX

| Library | Verdict |
|---|---|
| **python-pptx + lxml** | **Recommended.** Direct access to shapes, groups, placeholders, tables, notes, runs, and — through lxml — any raw XML (SmartArt `dgm`, chart XML) it does not model. Writing a copy preserves everything we don't touch. MIT licence. |
| .NET Open XML SDK | Equally faithful (raw OOXML). Would be the choice for a C# core. |
| Aspose.Slides | Best rendering/measurement, but commercial and closed. Not needed. |
| LibreOffice headless | Not for editing (round-trip loses fidelity). Useful later only for **rendering to PNG for visual overflow checks**. |

Rule: we modify **only `<a:t>` text and, when needed, run/paragraph size and `bodyPr` autofit attributes**. Everything else in the package is byte-preserved.

Element coverage plan:
- v1: text boxes, placeholders (title/body), grouped shapes (recursive), tables, speaker notes, `a:fld` fields left intact.
- v1.x: chart titles/axis/category labels (chart XML), SmartArt text (`dgm` data part — and its cached drawing must be updated too, which is tricky).
- Reported as not translated: text inside images, embedded OLE objects, WordArt effects that break with CJK.

### 4.2 PDF

| Library | Role | Licence |
|---|---|---|
| **PyMuPDF (fitz)** | Extraction with positions/fonts, redaction, `insert_htmlbox` for fitted text with CJK fonts | **AGPL-3.0** — fine for private/internal use; if the app is ever distributed, a commercial licence or a replacement is needed |
| pypdfium2 | Extraction/rendering alternative | Apache/BSD — clean |
| pdfplumber | Table-oriented extraction | MIT |
| **BabelDOC / PDFMathTranslate** | Existing open-source layout-preserving PDF translation; worth studying/reusing its layout logic | AGPL-3.0 |
| Docling (IBM) | Layout analysis (reading order, tables) | MIT |

Output strategy (Phase 3), in order of fidelity:
1. **In-place PDF**: redact original text per block → insert translated text in the same rect → shrink font to fit → flag blocks that could not fit.
2. **Fallback**: bilingual PDF (original page + translation overlay/annotations) or a DOCX with the translated text in reading order, when in-place fails.

### 4.3 OCR (scanned PDFs)

| Engine | Notes |
|---|---|
| **RapidOCR** (PaddleOCR models on ONNX Runtime) | Strong CJK accuracy, pip-installable on Windows, no PaddlePaddle dependency. Apache-2.0. **Recommended first choice.** |
| Windows built-in OCR (`Windows.Media.Ocr`) | Offline, zero download, decent Japanese if the JA language pack is installed. Good fallback. |
| Tesseract | Mature but weaker on Japanese layout. |
| Surya / docTR | Good quality, heavier (PyTorch). Later if needed. |

Detection: a page is "scanned" if it has little/no text layer but large image coverage. Per-page decision; mixed PDFs are common.

---

## 5. Application architecture options

Five options were evaluated against the stated criteria (1 = poor, 5 = excellent).

| Criterion | A. C#/.NET (WPF/WinUI) | B. Python core + web UI in WebView2 (pywebview) | C. Electron + Python sidecar | D. Tauri + Python sidecar | E. C# WPF shell + Python worker |
|---|---|---|---|---|---|
| Windows support | 5 | 5 | 5 | 5 | 5 |
| Offline operation | 5 | 5 | 5 | 5 | 5 |
| AI/ML ecosystem | 2 | 5 | 5 | 5 | 5 |
| PPTX processing | 5 (Open XML SDK) | 5 | 5 | 5 | 5 |
| PDF + OCR processing | 2 | 5 | 5 | 5 | 5 |
| UI quality (modern, dark/light, review grid) | 4 | 4 | 5 | 5 | 4 |
| Packaging simplicity | 5 | 4 (PyInstaller + installer) | 2 (~150 MB Chromium + Python) | 3 (Rust toolchain + sidecar) | 3 (two runtimes) |
| Maintenance (languages/moving parts) | 4 | **5 (Python + TS only)** | 3 | 3 (adds Rust) | 3 (C# + Python + IPC) |
| Your familiarity | 5 | 3 (HTML/CSS/JS yes, Python new-ish) | 4 | 3 | 5 |
| **Privacy surface** | 5 | **5 (in-process JS bridge, no HTTP port)** | 4 | 4 | 4 |

Why not A alone: PDF layout analysis, OCR, text metrics and the model ecosystem are all Python-first. A pure C# app would spend most of its effort re-implementing or wrapping Python tools.

Why not C: Electron adds ~150 MB and a second JS runtime for no benefit over WebView2, which is already on every Windows 11 machine.

D is a reasonable upgrade path later (nicer installer/auto-update), but adds Rust for little v1 gain.

### Recommendation: **Option B — Python core + TypeScript web UI hosted in WebView2 (pywebview)**

```
┌──────────────────────────────── SmartBuildingTranslator.exe ────────────────────────────────┐
│  UI (HTML/CSS/TypeScript, runs in WebView2)                                                  │
│      │  in-process JS↔Python bridge (no network socket)                                       │
│  ┌───▼──────────────────────────── Python core (sbt package) ─────────────────────────────┐  │
│  │ Application services: JobService, TerminologyService, ModelService, SettingsService    │  │
│  │                                                                                         │  │
│  │ Parsers ──► Document Model (segments + formatting + geometry) ──► Renderers             │  │
│  │  (pptx, pdf, ocr)                     │                          (pptx, pdf)            │  │
│  │                                       ▼                                                 │  │
│  │ Translation Pipeline: protect → terminology → context build → cache/TM → engine →       │  │
│  │                       unprotect/validate → quality checks → fit/overflow                │  │
│  │                                       │                                                 │  │
│  │ Engines: LlamaCppEngine │ OllamaEngine │ (later) OnlineEngine [consent-gated]           │  │
│  │ Storage: SQLite (terminology, TM, cache, jobs, settings) — %LOCALAPPDATA%\SBT           │  │
│  │ Privacy: NetworkGuard (offline mode = loopback-only sockets), content-free logging      │  │
│  └─────────────────────────────────────┬───────────────────────────────────────────────────┘  │
│                                        │ HTTP on 127.0.0.1 only                                │
│                           llama-server.exe (bundled, CUDA/CPU) + GGUF model files             │
└───────────────────────────────────────────────────────────────────────────────────────────────┘
```

Why:
- Uses the strongest ecosystem for the three priorities (ML, PPTX/PDF, OCR) in **one** language.
- UI is HTML/CSS/TypeScript, which you already know; WebView2 is built into Windows 11.
- No HTTP server of our own → nothing listening on the network; the only socket is the loopback link to `llama-server`.
- The core is a plain library + CLI first. The UI is a thin layer, so it can later move to Tauri or a C# WPF/WebView2 shell without touching the pipeline.

---

## 6. Module layout and interfaces

```
UI (ui/)                          ─ presentation only, no business logic
sbt/app/        services          ─ orchestrates jobs, exposes API to UI & CLI
sbt/domain/     models            ─ Segment, Run, TextBlock, DocumentModel, Job, Warnings
sbt/parsers/    DocumentParser    ─ pptx_parser, pdf_parser, ocr
sbt/renderers/  DocumentRenderer  ─ pptx_renderer, pdf_renderer, text_fit
sbt/pipeline/   TranslationPipeline, context builder, batching
sbt/protection/ ProtectedTokenMasker (acronyms, URLs, IPs, part numbers, DNT terms)
sbt/terminology/Glossary, TermMatcher (longest-match, case/inflection aware)
sbt/engines/    TranslationEngine + implementations, EngineRegistry
sbt/models_mgr/ LocalModelManager (catalogue, download, verify SHA-256, hardware fit)
sbt/quality/    QualityChecker (consistency, missing, tokens, tags, overflow)
sbt/storage/    SQLite repositories
sbt/privacy/    NetworkGuard, log redaction
sbt/hardware/   HardwareProbe (CPU, RAM, GPU/VRAM via nvidia-smi / DXGI)
```

Key interface (see `src/sbt/engines/base.py`):

```python
class TranslationEngine(Protocol):
    info: EngineInfo                       # id, is_local, supports_tags, supports_glossary, languages
    def translate(self, request: TranslationRequest) -> TranslationResult: ...
```

`EngineInfo.is_local` is enforced by the pipeline: in **Offline mode** only engines with `is_local=True` can be constructed, and `NetworkGuard` blocks every non-loopback socket in the process as a second line of defence.

---

## 7. Translation pipeline design

```
Document ─► Parse ─► Segments (paragraph-level, runs tagged <r1>…</r1>)
           │
           ├─ Pass 1: Document analysis
           │    • glossary matching over the whole document
           │    • candidate term mining (acronyms, Title-Case n-grams, repeated noun phrases)
           │    • translate unknown candidate terms ONCE → "document term sheet" (locked)
           │
           ├─ Pass 2: Translation, slide by slide
           │    • protect tokens → ⟦P1⟧, ⟦P2⟧ … (URLs, IPs, emails, model/part numbers, DNT terms)
           │    • cache / translation-memory lookup (exact hit → reuse)
           │    • prompt = style rules + relevant term-sheet entries only + slide title
           │               + neighbouring segments as read-only context + segments to translate
           │    • constrained JSON output (id → translation)
           │    • validate: placeholders all present, tags balanced, not source-copied,
           │                glossary targets present → retry once with the error named → else flag
           │    • unprotect
           │
           ├─ Pass 3: Quality checks (consistency, missing, overflow estimate)
           └─ Render ─► copy of original with translated text, fitted
```

Japanese style defaults (configurable): slide titles/bullets in **体言止め** (noun-ending), body sentences and notes in **です・ます**; full-width punctuation 、。; keep half-width for numbers/units/Latin identifiers; space rules between Latin and Japanese text follow the source document's convention.

Translation memory v1: SQLite exact match + fuzzy match (RapidFuzz) as prompt hints. **No vector DB in v1** — fuzzy string match over a few thousand rows is fast and sufficient. Revisit embeddings only if TM grows large and fuzzy match proves too weak.

---

## 8. Hardware requirements (to be validated by measurement in Phase 1)

| Tier | Hardware | Feasible model | Expectation |
|---|---|---|---|
| Minimum | 16 GB RAM, 4+ core CPU, no GPU | 3–4B Q4 (e.g. TranslateGemma 4B, CAT-Translate 3.3B) | Works, slow — likely minutes for a 20-slide deck. Lower quality. |
| **Your machine** | Ryzen 7 5700X, 32 GB RAM, **RTX 4060 8 GB** | 7–8B Q4/Q5 fully on GPU; 12B Q4 with partial offload | Good target for v1. Speed to be measured, not assumed. |
| Recommended for best local quality | 16–24 GB VRAM | 12–14B at Q6/Q8, or 27–32B Q4 | Noticeably better nuance on long sentences. |

Disk: 3–8 GB per model. No speed numbers are quoted here on purpose — the POC will record tokens/s and seconds per slide on your hardware.

---

## 9. Realistic offline quality

Honest expectation for a 7–12B local model **with** glossary, protected tokens and document context:

- **Terminology & identifiers**: can be made very reliable, because it is enforced by code (masking + glossary + validation), not trusted to the model.
- **Short slide fragments & bullets**: generally good; the main risk is wrong choice between near-synonyms (ビル管理 vs 建物管理, 空調機 vs エアハンドリングユニット) — which the glossary fixes.
- **Long technical sentences / speaker notes**: mostly correct meaning with occasional errors of omission, wrong modifier attachment, or stiff Japanese. This is where local models trail frontier cloud systems (GPT/Claude/Gemini class, DeepL).
- **JA→EN** is generally easier to get acceptable output for than **EN→JA**, where naturalness and register matter more.

Conclusion: **Mode A (offline) should be good enough for internal understanding and first drafts; documents for customers should go through the review screen.** Mode B (online, explicit) can be added later for higher quality on non-confidential content. The POC will confirm or refute this with numbers.

---

## 10. Phase 1 POC proposal

**Question to answer:** Can we produce sufficiently good EN→JA technical translation locally while preserving PPTX formatting?

**Scope (CLI only, no UI):**
```
python -m sbt.poc translate sample.pptx --to ja --engine llamacpp --model <gguf> --glossary data/terminology/smart_building_en_ja.csv
→ sample_JA.pptx + sample_JA.report.json
```

1. **Test deck generator** — script builds `sample.pptx` (≈12 slides) covering: the term list from the requirements, titles, multi-level bullets, mixed bold/italic/colour runs, a table, grouped shapes, speaker notes, numbers/units/percentages/dates, URLs, emails, IPs, part numbers, long sentences. Public, non-confidential content only. A Japanese source deck for JA→EN is built the same way.
2. **PPTX parser/renderer** — paragraph-level segments with run tags; write back to a copy; leave all untouched XML intact.
3. **Protection + glossary** — masker and longest-match glossary injection.
4. **Engine adapter** — `llama-server` (primary) and Ollama (optional) via their local OpenAI-compatible APIs; JSON-constrained output.
5. **Model bake-off** — same deck through Qwen3-8B, TranslateGemma 12B (and 4B), Hy-MT 7B (after licence check), CAT-Translate 7B.
6. **Measurement** — see §11.

**Explicitly out of scope for Phase 1:** PDF, OCR, UI, model downloader, TM, packaging.

**Deliverable:** a short `eval/results/phase1.md` with the scorecard per model, representative good/bad examples, and a go/no-go recommendation.

---

## 11. Evaluation method (measurable, not "looks good")

**Test set:** ~150 segments from the generated decks, categorised (term, fragment, sentence, number/unit, identifier, table cell, note). **Reference translations must be approved by you** (you are the domain expert) — I will draft them, you correct them.

**Automatic metrics (every run):**
| Metric | Target for "go" (proposed — you confirm) |
|---|---|
| Protected-token integrity (URLs, IPs, part numbers, acronyms unchanged) | 100 % (enforced; failures are bugs) |
| Glossary adherence (expected target term present) | ≥ 98 % |
| Run-tag integrity (formatting mapped correctly) | ≥ 95 %, remainder falls back with warning |
| Untranslated / source-copied segments | 0 unflagged |
| Overflow estimate | reported, not a gate in Phase 1 |
| chrF++ vs reference | tracked for relative comparison between models only |

**Human review (sample of 50 segments per model, MQM-lite):** each error tagged as *terminology / mistranslation / omission / addition / unnatural Japanese / wrong register / formatting* with severity *critical / major / minor*. Proposed go criteria: **0 critical, ≤ 5 major per 50 segments** for the chosen model.

**Loop:** run → score → log errors in `eval/results/` → fix pipeline (prompt, glossary, validation) → rerun. Cloud engines may be used for comparison **only on the public generated test deck**, never on your documents.

---

## 12. Decisions needed from you before Phase 1

1. Confirm the recommended architecture (Option B: Python core + web UI in WebView2).
2. Confirm the model shortlist and whether this is for work use at a large company (affects PLaMo/Hy-MT licensing).
3. Confirm the go/no-go thresholds in §11.
4. OK to install Python dev dependencies and download ~5–8 GB of GGUF models + `llama-server` from their official Hugging Face / GitHub release pages (each download will be confirmed individually).
