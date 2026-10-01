"""Format-independent document model shared by parsers, pipeline and renderers."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SegmentKind(Enum):
    TITLE = "title"
    BODY = "body"
    TABLE_CELL = "table_cell"
    NOTE = "note"


@dataclass
class Segment:
    """One translatable unit — a paragraph.

    `source` uses inline tags for formatting: text in the paragraph's dominant formatting is untagged,
    other formatting classes are wrapped as <g1>…</g1>, <g2>…</g2>. Line breaks are "\n".
    `id` is stable for a given source file so the renderer can find the paragraph again.
    """
    id: str
    kind: SegmentKind
    container: int                    # slide number (1-based) / page number
    shape_key: str                    # groups paragraphs of the same text frame
    source: str
    tag_ids: frozenset[int] = frozenset()
    translation: str | None = None    # tagged target text
    formatting_simplified: bool = False

    @property
    def plain_source(self) -> str:
        from sbt.pipeline.tags import strip_tags
        return strip_tags(self.source)


@dataclass
class DocumentModel:
    source_path: str
    file_type: str
    container_count: int
    segments: list[Segment] = field(default_factory=list)
    untranslatable: list[str] = field(default_factory=list)   # e.g. "slide 4: picture (text not translated)"


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Issue:
    """A quality/processing finding. `message` must never contain document text."""
    code: str
    severity: Severity
    segment_id: str | None
    message: str
