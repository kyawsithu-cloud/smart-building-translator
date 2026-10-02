"""Download Phase 1 runtime + models from pinned official URLs and verify SHA-256.

Every file is pinned to an exact release/commit and the SHA-256 published by GitHub / Hugging Face.
A file whose hash does not match is deleted. Executables are additionally scanned by Windows Defender.

Usage:  py -3.13 scripts/download_phase1.py [--only NAME ...]
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "runtime"
DEFENDER = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    sha256: str
    dest: Path
    unzip_to: Path | None = None   # executables: extracted and virus-scanned


LLAMA_TAG = "b11282"
GH = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
HF = "https://huggingface.co"

ASSETS = [
    Asset("llama-cuda",
          f"{GH}/llama-{LLAMA_TAG}-bin-win-cuda-13.4-x64.zip",
          "acd798f52fe8a8ce36d77b39a70cc061dbce45f12f440b8082fdde9803fc7921",
          ROOT / "downloads" / f"llama-{LLAMA_TAG}-bin-win-cuda-13.4-x64.zip", ROOT / "llama"),
    Asset("cudart",
          f"{GH}/cudart-llama-bin-win-cuda-13.4-x64.zip",
          "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668",
          ROOT / "downloads" / "cudart-llama-bin-win-cuda-13.4-x64.zip", ROOT / "llama"),
    Asset("hy-mt2-7b",
          f"{HF}/tencent/Hy-MT2-7B-GGUF/resolve/ab8472660ac61fac25f1af43fac2599d52a8a775/HY-MT2-7B-Q6_K.gguf",
          "88ef0aba59952a4cfe4be36cb5baf797dbb370bc60e9dcbd7297036021e52831",
          ROOT / "models" / "HY-MT2-7B-Q6_K.gguf"),
    # Optional OCR recognisers (Korean, Thai) — RapidOCR's official model host; SHA-256 as published in the
    # rapidocr package (default_models.yaml). English/Japanese/Chinese/Latin OCR models ship inside rapidocr.
    Asset("ocr-ko",
          "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx",
          "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
          ROOT / "ocr" / "korean_PP-OCRv5_rec_mobile.onnx"),
    Asset("ocr-th",
          "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/th_PP-OCRv5_rec_mobile.onnx",
          "de541dd83161c241ff426f7ecfd602a0ba77d686cf3ab9a6c255ea82fd08006e",
          ROOT / "ocr" / "th_PP-OCRv5_rec_mobile.onnx"),
    Asset("qwen3-8b",
          f"{HF}/Qwen/Qwen3-8B-GGUF/resolve/7c41481f57cb95916b40956ab2f0b139b296d974/Qwen3-8B-Q5_K_M.gguf",
          "068bae163faa96ad48032daf4e071a6a28fe67d8dcc95367609c2ff165e52738",
          ROOT / "models" / "Qwen3-8B-Q5_K_M.gguf"),
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(asset: Asset) -> None:
    asset.dest.parent.mkdir(parents=True, exist_ok=True)
    if asset.dest.exists() and sha256_of(asset.dest) == asset.sha256:
        print(f"[{asset.name}] already present, hash OK")
        return
    part = asset.dest.with_suffix(asset.dest.suffix + ".part")
    start = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(asset.url, headers={"Range": f"bytes={start}-"} if start else {})
    with urllib.request.urlopen(req) as resp, part.open("ab" if start else "wb") as out:
        if start and resp.status != 206:   # server ignored Range: restart
            out.seek(0), out.truncate()
            start = 0
        total = start + int(resp.headers.get("Content-Length", 0))
        done, last = start, -1
        while chunk := resp.read(4 * 1024 * 1024):
            out.write(chunk)
            done += len(chunk)
            pct = done * 100 // total if total else 0
            if pct // 10 != last:
                last = pct // 10
                print(f"[{asset.name}] {pct}% of {total // 1048576} MB", flush=True)
    actual = sha256_of(part)
    if actual != asset.sha256:
        part.unlink()
        raise RuntimeError(f"[{asset.name}] SHA-256 MISMATCH — file deleted. expected {asset.sha256} got {actual}")
    part.replace(asset.dest)
    print(f"[{asset.name}] SHA-256 verified")


def extract_and_scan(asset: Asset) -> None:
    if asset.unzip_to is None:
        return
    asset.unzip_to.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(asset.dest) as z:
        z.extractall(asset.unzip_to)
    if not DEFENDER.exists():
        print(f"[{asset.name}] WARNING: Windows Defender CLI not found; scan skipped")
        return
    r = subprocess.run([str(DEFENDER), "-Scan", "-ScanType", "3", "-File", str(asset.unzip_to),
                        "-DisableRemediation"], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"[{asset.name}] Defender scan reported a problem:\n{r.stdout}\n{r.stderr}")
    print(f"[{asset.name}] Windows Defender scan: no threats found")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", nargs="*")
    args = p.parse_args()
    for a in ASSETS:
        if args.only and a.name not in args.only:
            continue
        download(a)
        extract_and_scan(a)
    print("All done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
