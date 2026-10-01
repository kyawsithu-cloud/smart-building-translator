from __future__ import annotations

from pathlib import Path
from typing import Protocol

from sbt.domain.models import DocumentModel


class DocumentParser(Protocol):
    file_types: frozenset[str]

    def parse(self, path: Path) -> DocumentModel: ...
