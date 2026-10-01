"""Hardware detection: CPU, RAM, NVIDIA GPU/VRAM, OS. Local queries only (registry, Win32 API, nvidia-smi)."""
from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Gpu:
    name: str
    vram_total_mib: int
    vram_free_mib: int
    driver: str


@dataclass(frozen=True)
class Hardware:
    os: str
    cpu: str
    cores: int
    ram_gib: float
    gpus: tuple[Gpu, ...]

    @property
    def best_gpu(self) -> Gpu | None:
        return max(self.gpus, key=lambda g: g.vram_total_mib) if self.gpus else None


def _cpu_name() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
    except OSError:
        return platform.processor() or "unknown"


def _ram_gib() -> float:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        stat = MemoryStatus()
        stat.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
        return round(stat.ullTotalPhys / 2**30, 1)
    except (AttributeError, OSError):
        return 0.0


def nvidia_gpus() -> tuple[Gpu, ...]:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    gpus = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4 and parts[1].isdigit():
            gpus.append(Gpu(parts[0], int(parts[1]), int(parts[2]), parts[3]))
    return tuple(gpus)


def free_vram_mib() -> int | None:
    gpus = nvidia_gpus()
    return max(g.vram_free_mib for g in gpus) if gpus else None


def detect() -> Hardware:
    return Hardware(f"{platform.system()} {platform.release()} ({platform.version()})", _cpu_name(),
                    os.cpu_count() or 0, _ram_gib(), nvidia_gpus())
