"""Download the translation engine and models from pinned official URLs and verify SHA-256.

Every file is pinned to an exact release/commit and the SHA-256 published by GitHub / Hugging Face.
A file whose hash does not match is deleted. Executables are additionally scanned by Windows Defender.
Files go to the runtime folder (sbt.settings.runtime_dir()).

Usage:  python -m sbt download [--only NAME ...]      (packaged app: sbt.exe download …)
Runs in its own process: the app's own process never connects to the internet.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sbt.settings import runtime_dir

DEFENDER = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    sha256: str
    dest: str                      # relative to the runtime folder
    unzip_to: str | None = None    # executables: extracted and virus-scanned


LLAMA_TAG = "b11282"
GH = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
HF = "https://huggingface.co"

ASSETS = [
    Asset("llama-cuda",
          f"{GH}/llama-{LLAMA_TAG}-bin-win-cuda-13.4-x64.zip",
          "acd798f52fe8a8ce36d77b39a70cc061dbce45f12f440b8082fdde9803fc7921",
          f"downloads/llama-{LLAMA_TAG}-bin-win-cuda-13.4-x64.zip", "llama"),
    Asset("cudart",
          f"{GH}/cudart-llama-bin-win-cuda-13.4-x64.zip",
          "738f8c251ac22b70c3ae6f83a10cf222725df0395246a2cf58f32bdb85fbe668",
          "downloads/cudart-llama-bin-win-cuda-13.4-x64.zip", "llama"),
    Asset("hy-mt2-7b",
          f"{HF}/tencent/Hy-MT2-7B-GGUF/resolve/ab8472660ac61fac25f1af43fac2599d52a8a775/HY-MT2-7B-Q6_K.gguf",
          "88ef0aba59952a4cfe4be36cb5baf797dbb370bc60e9dcbd7297036021e52831",
          "models/HY-MT2-7B-Q6_K.gguf"),
    # Optional OCR recognisers (Korean, Thai) — RapidOCR's official model host; SHA-256 as published in the
    # rapidocr package (default_models.yaml). English/Japanese/Chinese/Latin OCR models ship inside rapidocr.
    Asset("ocr-ko",
          "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile.onnx",
          "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
          "ocr/korean_PP-OCRv5_rec_mobile.onnx"),
    Asset("ocr-th",
          "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv5/rec/th_PP-OCRv5_rec_mobile.onnx",
          "de541dd83161c241ff426f7ecfd602a0ba77d686cf3ab9a6c255ea82fd08006e",
          "ocr/th_PP-OCRv5_rec_mobile.onnx"),
    Asset("qwen3-8b",
          f"{HF}/Qwen/Qwen3-8B-GGUF/resolve/7c41481f57cb95916b40956ab2f0b139b296d974/Qwen3-8B-Q5_K_M.gguf",
          "068bae163faa96ad48032daf4e071a6a28fe67d8dcc95367609c2ff165e52738",
          "models/Qwen3-8B-Q5_K_M.gguf"),
]


# Approximate download sizes (MB), for one overall progress bar over several files.
SIZE_MB = {"llama-cuda": 145, "cudart": 404, "hy-mt2-7b": 5879, "ocr-ko": 13, "ocr-th": 8, "qwen3-8b": 5580}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(asset: Asset, root: Path) -> None:
    dest = root / asset.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) == asset.sha256:
        print(f"[{asset.name}] already present, hash OK")
        return
    part = dest.with_suffix(dest.suffix + ".part")
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
    part.replace(dest)
    print(f"[{asset.name}] SHA-256 verified")


def extract_and_scan(asset: Asset, root: Path) -> None:
    if asset.unzip_to is None:
        return
    target = root / asset.unzip_to
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(root / asset.dest) as z:
        z.extractall(target)
    found = defender_scan(target)
    if found is None:
        print(f"[{asset.name}] WARNING: Windows Defender CLI not found; scan skipped")
        return
    if found:
        raise RuntimeError(f"[{asset.name}] Defender scan reported a problem:\n{found}")
    print(f"[{asset.name}] Windows Defender scan: no threats found")


def defender_scan(folder: Path) -> str | None:
    """Scans a folder with Windows Defender: "" = no threats, a report = problem, None = Defender not available."""
    if not DEFENDER.exists():
        return None
    r = subprocess.run([str(DEFENDER), "-Scan", "-ScanType", "3", "-File", str(folder), "-DisableRemediation"],
                       capture_output=True, text=True, check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return "" if r.returncode == 0 else f"{r.stdout}\n{r.stderr}".strip()


def run(only: list[str] | None = None, root: Path | None = None) -> int:
    root = root or runtime_dir()
    unknown = set(only or []) - {a.name for a in ASSETS}
    if unknown:
        print(f"Unknown download(s): {', '.join(sorted(unknown))}. Known: {', '.join(a.name for a in ASSETS)}")
        return 2
    print(f"Downloading to {root}", flush=True)
    for a in ASSETS:
        if only and a.name not in only:
            continue
        download(a, root)
        extract_and_scan(a, root)
    print("All done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m sbt download")
    p.add_argument("--only", nargs="*", help="names: " + ", ".join(a.name for a in ASSETS))
    return run(p.parse_args(argv).only)
