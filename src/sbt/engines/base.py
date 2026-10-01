"""Translation engine interface. Implementations: LlamaCppEngine (local), later OnlineEngine (consent-gated)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sbt.terminology.glossary import Hint


@dataclass(frozen=True)
class EngineInfo:
    id: str
    model: str
    is_local: bool                    # False => blocked in offline mode, needs per-job consent
    languages: frozenset[str]


@dataclass(frozen=True)
class TranslationItem:
    id: str
    text: str                         # source text, possibly with <g1> tags / <x1/> placeholders
    hints: tuple[Hint, ...] = ()
    is_heading: bool = False          # titles/bullets vs full sentences (affects Japanese style)
    feedback: str = ""                # validation problems from a previous attempt


@dataclass(frozen=True)
class TranslationRequest:
    source_lang: str
    target_lang: str
    items: list[TranslationItem]
    context: list[str] = field(default_factory=list)   # read-only neighbouring text (slide title etc.)
    previous: list[tuple[str, str]] = field(default_factory=list)  # (source, translation) already done nearby


@dataclass
class EngineStats:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class TranslationResult:
    translations: dict[str, str]      # item id -> raw target text
    failed_ids: list[str]


class TranslationEngine(Protocol):
    @property
    def info(self) -> EngineInfo: ...

    stats: EngineStats

    def translate(self, request: TranslationRequest) -> TranslationResult: ...
