from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sbt.domain.models import DocumentModel, Issue


class DocumentRenderer(Protocol):
    """Writes translations into a COPY of the source. Must never modify `model.source_path`."""
    file_types: frozenset[str]

    def render(self, model: DocumentModel, output_path: Path) -> list[Issue]: ...
