"""Local model catalogue for Phase 1. Temperature 0 (greedy) so the same document always gives the same
translation — needed for reliable evaluation; other sampling values follow each model card."""
from __future__ import annotations

from dataclasses import dataclass, field

ALL_9 = frozenset({"en", "ja", "zh", "ko", "my", "th", "de", "fr", "es"})


@dataclass(frozen=True)
class ModelProfile:
    id: str
    file: str
    prompt_style: str                 # "hymt" | "qwen_json" | "cat"
    languages: frozenset[str]
    licence: str
    ctx: int = 8192
    sampling: dict[str, float | int] = field(default_factory=dict)
    server_args: tuple[str, ...] = ()


PROFILES: dict[str, ModelProfile] = {p.id: p for p in [
    ModelProfile("hy-mt2-7b", "HY-MT2-7B-Q6_K.gguf", "hymt", ALL_9, "Apache-2.0",
                 sampling={"temperature": 0.0, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05}),
    ModelProfile("qwen3-8b", "Qwen3-8B-Q5_K_M.gguf", "qwen_json", ALL_9, "Apache-2.0",
                 sampling={"temperature": 0.0, "top_p": 0.8, "top_k": 20},
                 server_args=("--reasoning", "off")),
    # cat-translate-7b removed after Phase 1: it altered identifiers (HVAC→HVAAC, URLs). See PHASE1_RESULTS.md.
]}
