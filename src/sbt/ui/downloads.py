"""Model downloads from the Models screen.

Downloads run in a separate process (`sbt download`, see sbt/download.py: pinned URLs, SHA-256 check,
Defender scan of program files). The UI process — which holds document content — keeps its network guard on and never connects
to the internet itself. Nothing is downloaded without an explicit click and confirmation.
"""
from __future__ import annotations

import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sbt.engines.llama_server import engine_path, model_path
from sbt.engines.profiles import PROFILES
from sbt.settings import FROZEN, runtime_dir

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


def _file(item_id: str) -> Path:
    """The file that shows a component is installed (looked up each time: the models folder can change)."""
    return {"hy-mt2-7b": lambda: model_path(PROFILES["hy-mt2-7b"]), "qwen3-8b": lambda: model_path(PROFILES["qwen3-8b"]),
            "ocr-ko": lambda: runtime_dir() / "ocr" / "korean_PP-OCRv5_rec_mobile.onnx",
            "ocr-th": lambda: runtime_dir() / "ocr" / "th_PP-OCRv5_rec_mobile.onnx",
            "engine": engine_path}[item_id]()


def command(assets: tuple[str, ...]) -> list[str]:
    """The downloader process: sbt.exe next to the packaged app, or `python -m sbt` in development."""
    if FROZEN:
        return [str(Path(sys.executable).with_name("sbt.exe")), "download", "--only", *assets]
    return [sys.executable, "-u", "-m", "sbt", "download", "--only", *assets]


def installed(item_id: str) -> bool:
    return _file(item_id).exists()


def deletable(item_id: str) -> bool:
    return item_id in ("qwen3-8b", "ocr-ko", "ocr-th", "hy-mt2-7b")


def delete(item_id: str) -> None:
    if not deletable(item_id):
        raise ValueError("This component cannot be deleted from the app")
    _file(item_id).unlink(missing_ok=True)


@dataclass
class DownloadState:
    item: str = ""
    status: str = "idle"           # idle | running | done | failed | cancelled
    asset: str = ""                # file being downloaded now
    percent: int = 0               # of that file
    overall: int = 0               # of everything in this run (by size)
    total_mb: int = 0
    finished: list[str] = field(default_factory=list)   # files downloaded and verified
    message: str = ""
    log: list[str] = field(default_factory=list)


class Downloader:
    """Runs `sbt download --only …` in a separate process and follows its progress lines."""

    def __init__(self) -> None:
        self.state = DownloadState()
        self._proc: subprocess.Popen[str] | None = None
        self._sizes: dict[str, int] = {}
        self._done: dict[str, int] = {}

    def start(self, item_id: str) -> None:
        item = next((i for i in CATALOGUE if i.id == item_id), None)
        if item is None:
            raise ValueError("Unknown download")
        self.start_assets(item.assets, item_id)

    def start_assets(self, assets: tuple[str, ...], label: str) -> None:
        """Several files in one run (the setup guide): one overall progress bar."""
        from sbt.download import SIZE_MB
        if self.state.status == "running":
            raise RuntimeError("A download is already running")
        if not assets:
            raise ValueError("Nothing to download")
        self._sizes = {a: SIZE_MB.get(a, 100) for a in assets}
        self._done = dict.fromkeys(assets, 0)
        self.state = DownloadState(item=label, status="running", total_mb=sum(self._sizes.values()))
        self._proc = subprocess.Popen(command(assets), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                      encoding="utf-8", errors="replace",
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._follow, daemon=True).start()

    def cancel(self) -> None:
        if self._proc is not None and self.state.status == "running":
            self.state.status = "cancelled"
            self._proc.terminate()          # a partly downloaded file is kept as .part and resumed next time

    def _progress(self, name: str, pct: int) -> None:
        if name in self._done:
            self._done[name] = self._sizes[name] * pct // 100
            total = sum(self._sizes.values())
            self.state.overall = min(100, sum(self._done.values()) * 100 // total) if total else 0

    def _follow(self) -> None:
        assert self._proc and self._proc.stdout
        for raw in self._proc.stdout:
            line = raw.strip()
            m = _LINE.match(line)
            if m and m.group("pct"):
                self.state.asset, self.state.percent = m.group("name"), int(m.group("pct"))
                self._progress(m.group("name"), int(m.group("pct")))
            elif line:
                if m and ("verified" in line or "hash OK" in line):
                    self._progress(m.group("name"), 100)
                    self.state.finished.append(m.group("name"))
                self.state.message = line[:200]
                self.state.log.append(line[:200])
        code = self._proc.wait()
        if self.state.status == "cancelled":
            self.state.message = "Download cancelled"
        elif code == 0:
            self.state.status, self.state.percent, self.state.overall = "done", 100, 100
            self.state.message = "Installed and verified"
        else:
            self.state.status = "failed"
            self.state.message = next((ln for ln in reversed(self.state.log) if "MISMATCH" in ln or "Error" in ln),
                                      "Download failed — check the internet connection and try again")
