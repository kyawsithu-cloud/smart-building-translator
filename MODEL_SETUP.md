# Model Setup

The app talks to a bundled llama.cpp `llama-server` started on `127.0.0.1` with `--offline` (it cannot fetch
anything) and `--no-webui`. It is started and stopped automatically for each job.

**Roles:** `hy-mt2-7b` translates. `qwen3-8b` (optional) is the repair engine: it re-translates only paragraphs
that are still flagged after retries (Phase 2: it fixed the one remaining omission on the test deck). It is not
used for Burmese, where it was measured to be poor. Check what is installed with `python -m sbt doctor`.

## Where the engine and models are kept
| Running | Models folder |
|---|---|
| installed app | `%LOCALAPPDATA%\SmartBuildingTranslator\runtime` |
| from the source folder | `runtime\` in this folder |
| either, after *Models → Models folder → Change…* | the folder you chose (setting `runtime_dir`) |

The folder holds `llama\` (engine), `models\` (GGUF files), `ocr\` (optional OCR models) and `logs\`. A folder
copied from another PC (or this project's `runtime` folder) can be chosen directly — no download needed. Choosing
a folder on another drive also makes new downloads go there.

## Install
```
.venv\Scripts\python -m sbt download            # everything (installed app: sbt.exe download)
.venv\Scripts\python -m sbt download --only hy-mt2-7b
```
Files go to the models folder above (`runtime/` in the source folder, git-ignored). Every file is pinned to an exact GitHub release / Hugging Face commit and
checked against the SHA-256 published by that source; a mismatch deletes the file. The llama.cpp binaries are
also scanned with Windows Defender after extraction. GGUF model files are pure weight data (no executable code).

| Name | File | Size | Source | Licence | Languages |
|---|---|---|---|---|---|
| llama.cpp b11282 (CUDA 13.4) | llama-server.exe + DLLs | ~550 MB | github.com/ggml-org/llama.cpp | MIT | — |
| **hy-mt2-7b** | HY-MT2-7B-Q6_K.gguf | 5.9 GB | huggingface.co/tencent/Hy-MT2-7B-GGUF | Apache-2.0 | 33 incl. all 9 app languages |
| qwen3-8b | Qwen3-8B-Q5_K_M.gguf | 5.6 GB | huggingface.co/Qwen/Qwen3-8B-GGUF | Apache-2.0 | 100+ |

CAT-Translate-7B was tested in Phase 1 and removed: it altered identifiers such as HVAC and URLs.

## OCR (scanned PDFs, text in pictures)
Runs on the CPU with ONNX Runtime; about 1–3 s per page. Fully offline.
- **English, Japanese, Chinese and Latin-script languages**: the multilingual PP-OCRv6 models ship inside the
  `rapidocr` Python package — nothing to download.
- **Korean, Thai** (optional, 13 MB + 8 MB): `.venv\Scripts\python.exe -m sbt download --only ocr-ko ocr-th`
  (RapidOCR's official model host, checked against the SHA-256 published in the rapidocr package).
- **Burmese**: no OCR model exists in this family; scanned Burmese pages are reported as not translatable.

Measured accuracy on the public scanned test PDFs: see eval/results/PHASE3_RESULTS.md.

## Hardware notes
- RTX 4060 8 GB: each model runs fully on the GPU when about 7 GB is free (Hy-MT2 uses a 4k context, which is
  enough because it translates one paragraph at a time). If a game or other app is using GPU memory, the app
  automatically puts part of the model on the CPU instead of slowing to a crawl. The two models are never
  loaded at the same time.
- No NVIDIA GPU: use the CPU build of llama.cpp and a smaller quantisation (Q4_K_M); expect it to be much slower.

## Adding a model
Add a `ModelProfile` in `src/sbt/engines/profiles.py` (file, prompt style, languages, sampling) and a pinned
entry in `src/sbt/download.py`. If the model needs a new prompt format, add a builder in
`src/sbt/engines/prompts.py`.
