"""Starts and stops a bundled llama-server bound to 127.0.0.1 in offline mode."""
from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import httpx

from sbt.engines.profiles import ModelProfile

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "runtime"


def free_vram_mib() -> int | None:
    """Free memory on the first NVIDIA GPU, or None if it cannot be read."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=subprocess.CREATE_NO_WINDOW).stdout
        return int(out.split()[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def choose_gpu_layers(model: Path, ctx_mib: int = 1300) -> str:
    """'all' when the whole model + context fits in currently free VRAM (fastest); otherwise 'auto', which lets
    llama.cpp put what fits on the GPU and the rest on the CPU instead of spilling into slow shared memory."""
    free = free_vram_mib()
    need = model.stat().st_size // 2**20 + ctx_mib + 300
    return "all" if free is not None and free >= need else "auto"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LlamaServer:
    def __init__(self, profile: ModelProfile, gpu_layers: str | None = None) -> None:
        self.profile = profile
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.gpu_layers = gpu_layers          # None = decide from free VRAM at start-up
        self._proc: subprocess.Popen[bytes] | None = None
        self.log_path = RUNTIME / "logs" / f"llama-server-{profile.id}.log"

    def __enter__(self) -> LlamaServer:
        model = RUNTIME / "models" / self.profile.file
        exe = RUNTIME / "llama" / "llama-server.exe"
        if not model.exists():
            raise FileNotFoundError(f"Model not installed: {model.name} (run scripts/download_phase1.py)")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.gpu_layers is None:
            self.gpu_layers = choose_gpu_layers(model)
        args = [str(exe), "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
                "-ngl", self.gpu_layers, "-c", str(self.profile.ctx), "--offline", "--no-webui",
                "-np", "1", *self.profile.server_args]
        log = self.log_path.open("wb")
        self._proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
        where = {"all": "GPU", "0": "CPU only"}.get(self.gpu_layers, "GPU + CPU (GPU memory is partly in use)")
        print(f"Loading the translation model on {where}...", flush=True)
        deadline = time.time() + 300
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"llama-server exited during start-up; see {self.log_path}")
            try:
                if httpx.get(f"{self.url}/health", timeout=2, trust_env=False).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise TimeoutError("llama-server did not become ready within 300 s")

    def __exit__(self, *exc: object) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._proc.kill()
