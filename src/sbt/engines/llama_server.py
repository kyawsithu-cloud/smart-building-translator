"""Starts and stops the bundled llama-server: bound to 127.0.0.1, offline, no web UI."""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import IO

import httpx

from sbt.engines.profiles import ModelProfile
from sbt.hardware.probe import free_vram_mib
from sbt.settings import runtime_dir


def engine_path() -> Path:
    return runtime_dir() / "llama" / "llama-server.exe"


def model_path(profile: ModelProfile) -> Path:
    return runtime_dir() / "models" / profile.file


def vram_needed_mib(profile: ModelProfile) -> int:
    """Model weights + KV cache (~1.1 GiB per 8k tokens for these 7–8B models) + compute buffers + margin."""
    path = model_path(profile)
    size = path.stat().st_size // 2**20 if path.exists() else 6000
    return size + profile.ctx * 1100 // 8192 + 400


def choose_gpu_layers(profile: ModelProfile) -> str:
    """'all' when the whole model + context fits in currently free VRAM (fastest); otherwise 'auto', which lets
    llama.cpp put what fits on the GPU and the rest on the CPU instead of spilling into slow shared memory."""
    free = free_vram_mib()
    return "all" if free is not None and free >= vram_needed_mib(profile) else "auto"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LlamaServer:
    def __init__(self, profile: ModelProfile, gpu_layers: str | None = None) -> None:
        self.profile = profile
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.gpu_layers = gpu_layers          # None = decide from free VRAM at start-up; "0" = CPU only
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None
        self.log_path = runtime_dir() / "logs" / f"llama-server-{profile.id}.log"

    def __enter__(self) -> LlamaServer:
        model = model_path(self.profile)
        exe = engine_path()
        if not exe.exists():
            raise FileNotFoundError(f"Translation engine not installed: {exe}")
        if not model.exists():
            raise FileNotFoundError(f"Model not installed: {model.name} (see MODEL_SETUP.md)")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.gpu_layers is None:
            self.gpu_layers = choose_gpu_layers(self.profile)
        args = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                "-ngl", self.gpu_layers, "-c", str(self.profile.ctx), "--offline", "--no-webui",
                "-np", "1", *self.profile.server_args]
        self._log = self.log_path.open("wb")
        self._proc = subprocess.Popen(args, stdout=self._log, stderr=subprocess.STDOUT,
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        where = {"all": "GPU", "0": "CPU only"}.get(self.gpu_layers, "GPU + CPU (GPU memory is partly in use)")
        print(f"Loading {self.profile.id} on {where}...", flush=True)
        deadline = time.time() + 300
        while time.time() < deadline:
            if self._proc.poll() is not None:
                self.__exit__()
                raise RuntimeError(f"llama-server exited during start-up; see {self.log_path}")
            try:
                if httpx.get(f"{self.url}/health", timeout=2, trust_env=False).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(1)
        self.__exit__()
        raise TimeoutError("llama-server did not become ready within 300 s")

    def __exit__(self, *exc: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._log:
            self._log.close()
            self._log = None
