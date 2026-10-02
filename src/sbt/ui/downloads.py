"""Model downloads from the Models screen.

Downloads run in a separate process (scripts/download_phase1.py: pinned URLs, SHA-256 check, Defender scan of
program files). The UI process — which holds document content — keeps its network guard on and never connects
to the internet itself. Nothing is downloaded without an explicit click and confirmation.
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field

from sbt.engines.llama_server import RUNTIME, model_path
from sbt.engines.profiles import PROFILES
from sbt.settings import PROJECT_ROOT

SCRIPT = PROJECT_ROOT / "scripts" / "download_phase1.py"
_LINE = re.compile(r"^\[(?P<name>[\w.-]+)\] (?:(?P<pct>\d+)% of (?P<mb>\d+) MB|(?P<msg>.+))$")


@dataclass(frozen=True)
class Item:
    id: str
    label: str
    assets: tuple[str, ...]
    size: str
    source: str
    licence: str
    purpose: str


CATALOGUE = [
    Item("engine", "Translation engine (llama.cpp, CUDA)", ("llama-cuda", "cudart"), "0.6 GB",
         "github.com/ggml-org/llama.cpp (release b11282)", "MIT", "Runs the translation models"),
    Item("hy-mt2-7b", "Hy-MT2 7B — main translator", ("hy-mt2-7b",), "5.9 GB",
         "huggingface.co/tencent/Hy-MT2-7B-GGUF", "Apache-2.0", "Translates all 9 languages"),
    Item("qwen3-8b", "Qwen3 8B — repair model (optional)", ("qwen3-8b",), "5.6 GB",
         "huggingface.co/Qwen/Qwen3-8B-GGUF", "Apache-2.0", "Re-translates paragraphs that are still flagged"),
    Item("ocr-ko", "Korean OCR (optional)", ("ocr-ko",), "13 MB", "modelscope.cn/models/RapidAI/RapidOCR",
         "Apache-2.0", "Reads scanned Korean pages"),
    Item("ocr-th", "Thai OCR (optional)", ("ocr-th",), "8 MB", "modelscope.cn/models/RapidAI/RapidOCR",
         "Apache-2.0", "Reads scanned Thai pages"),
]
_FILES = {"hy-mt2-7b": model_path(PROFILES["hy-mt2-7b"]), "qwen3-8b": model_path(PROFILES["qwen3-8b"]),
          "ocr-ko": RUNTIME / "ocr" / "korean_PP-OCRv5_rec_mobile.onnx",
          "ocr-th": RUNTIME / "ocr" / "th_PP-OCRv5_rec_mobile.onnx",
          "engine": RUNTIME / "llama" / "llama-server.exe"}


def installed(item_id: str) -> bool:
    return _FILES[item_id].exists()


def deletable(item_id: str) -> bool:
    return item_id in ("qwen3-8b", "ocr-ko", "ocr-th", "hy-mt2-7b")


def delete(item_id: str) -> None:
    if not deletable(item_id):
        raise ValueError("This component cannot be deleted from the app")
    _FILES[item_id].unlink(missing_ok=True)


@dataclass
class DownloadState:
    item: str = ""
    status: str = "idle"           # idle | running | done | failed
    asset: str = ""
    percent: int = 0
    message: str = ""
    log: list[str] = field(default_factory=list)


class Downloader:
    def __init__(self) -> None:
        self.state = DownloadState()
        self._proc: subprocess.Popen[str] | None = None

    def start(self, item_id: str) -> None:
        item = next((i for i in CATALOGUE if i.id == item_id), None)
        if item is None:
            raise ValueError("Unknown download")
        if self.state.status == "running":
            raise RuntimeError("A download is already running")
        self.state = DownloadState(item=item_id, status="running")
        cmd = [sys.executable, "-u", str(SCRIPT), "--only", *item.assets]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      encoding="utf-8", errors="replace",
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._follow, daemon=True).start()

    def _follow(self) -> None:
        assert self._proc and self._proc.stdout
        for raw in self._proc.stdout:
            line = raw.strip()
            m = _LINE.match(line)
            if m and m.group("pct"):
                self.state.asset, self.state.percent = m.group("name"), int(m.group("pct"))
            elif line:
                self.state.message = line[:200]
                self.state.log.append(line[:200])
        code = self._proc.wait()
        if code == 0:
            self.state.status, self.state.percent, self.state.message = "done", 100, "Installed and verified"
        else:
            self.state.status = "failed"
            self.state.message = next((ln for ln in reversed(self.state.log) if "MISMATCH" in ln or "Error" in ln),
                                      "Download failed — check the internet connection and try again")
