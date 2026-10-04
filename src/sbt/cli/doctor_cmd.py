from __future__ import annotations

import argparse

from sbt.engines.llama_server import engine_path, model_path
from sbt.engines.profiles import PROFILES
from sbt.hardware.probe import detect
from sbt.hardware.recommend import recommend
from sbt.settings import Settings


def register(sub: argparse._SubParsersAction, cfg: Settings) -> None:  # type: ignore[type-arg]
    sub.add_parser("doctor", help="check hardware, models and recommend settings").set_defaults(func=run)


def run(args: argparse.Namespace, cfg: Settings) -> int:
    hw = detect()
    print("System")
    print(f"  OS:    {hw.os}\n  CPU:   {hw.cpu} ({hw.cores} threads)\n  RAM:   {hw.ram_gib} GB")
    if hw.gpus:
        for g in hw.gpus:
            print(f"  GPU:   {g.name}, {g.vram_total_mib} MiB VRAM ({g.vram_free_mib} MiB free now), "
                  f"driver {g.driver}")
    else:
        print("  GPU:   no NVIDIA GPU detected")

    engine = engine_path()
    print("\nTranslation engine")
    print(f"  llama-server: {'installed' if engine.exists() else 'NOT installed'}")
    print("\nModels")
    for p in PROFILES.values():
        path = model_path(p)
        state = f"installed, {path.stat().st_size / 2**30:.1f} GB" if path.exists() else "not installed"
        mark = "*" if p.id == cfg.model else " "
        langs = ", ".join(sorted(p.languages))
        print(f" {mark} {p.id:<11} {state:<24} {p.licence:<11} {langs}")

    rec = recommend(hw, cfg.model)
    print(f"\nRecommendation for {rec.model}: run on {rec.placement}")
    print(f"  {rec.expectation}")
    for n in rec.notes:
        print(f"  ! {n}")
    print(f"\nSettings: model={cfg.model}, repair_model={cfg.repair_model or '-'}, glossary={cfg.glossary}, "
          f"doc_terms={cfg.doc_terms}, memory={'on' if cfg.use_memory else 'off'}, gpu={cfg.gpu}")
    print(f"Your data (glossary, memory, history): {cfg.db_path.parent}")
    print(f"Your settings file (optional): {cfg.user_file}")
    return 0
