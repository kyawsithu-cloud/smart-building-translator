"""Model recommendation from detected hardware. Speeds quoted are measurements, labelled with their machine."""
from __future__ import annotations

from dataclasses import dataclass

from sbt.engines.llama_server import model_path, vram_needed_mib
from sbt.engines.profiles import PROFILES
from sbt.hardware.probe import Hardware

REFERENCE = "measured on Ryzen 7 5700X + RTX 4060 8 GB, 9-slide test deck"
MEASURED = {   # model id -> (full GPU, CPU only)
    "hy-mt2-7b": ("~30 tok/s, 20–40 s per deck", "~3 tok/s, about 4–5 min per deck"),
    "qwen3-8b": ("~39 tok/s, 45–60 s per deck (batched prompts are longer)", "not measured"),
}


@dataclass(frozen=True)
class Recommendation:
    model: str
    placement: str          # "GPU" | "GPU + CPU" | "CPU"
    expectation: str
    notes: tuple[str, ...]


def recommend(hw: Hardware, model: str = "hy-mt2-7b") -> Recommendation:
    profile = PROFILES[model]
    path = model_path(profile)
    need = vram_needed_mib(profile)
    gpu = hw.best_gpu
    notes: list[str] = []
    gpu_speed, cpu_speed = MEASURED.get(model, ("not measured", "not measured"))
    if not path.exists():
        notes.append(f"{profile.file} is not installed (see MODEL_SETUP.md).")
    if hw.ram_gib and hw.ram_gib < 12:
        notes.append(f"Only {hw.ram_gib} GB RAM: a 7B model needs about 8 GB free; close other programs.")
    if gpu and gpu.vram_total_mib >= need:
        if gpu.vram_free_mib < need:
            notes.append(f"Right now {gpu.vram_free_mib} MiB of {gpu.vram_total_mib} MiB VRAM is free and "
                         f"{need} MiB is needed: other programs (browser, games, video) are using the GPU, so "
                         "part of the model will run on the CPU (slower). Close them for full speed.")
        return Recommendation(model, "GPU", f"Good. {gpu_speed} ({REFERENCE}).", tuple(notes))
    if gpu and gpu.vram_total_mib >= 4000:
        notes.append("A smaller quantisation (Q4_K_M, ~4.4 GB) would fit fully on this GPU; not installed.")
        return Recommendation(model, "GPU + CPU", "Usable; between the GPU and CPU figures below "
                              f"({REFERENCE}): GPU {gpu_speed}; CPU {cpu_speed}.", tuple(notes))
    notes.append("No NVIDIA GPU with enough memory was found; translation runs on the CPU.")
    return Recommendation(model, "CPU", f"Slow but works. {cpu_speed} ({REFERENCE}).", tuple(notes))
