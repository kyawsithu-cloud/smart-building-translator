from __future__ import annotations

from pathlib import Path

from pptx import Presentation

from sbt.domain.models import DocumentModel, Segment
from sbt.parsers.pptx_walk import encode_paragraph, walk
from sbt.pipeline.tags import tag_ids


class PptxParser:
    file_types = frozenset({"pptx"})

    def parse(self, path: Path) -> DocumentModel:
        prs = Presentation(str(path))
        model = DocumentModel(str(path), "pptx", len(prs.slides))
        for item in walk(prs):
            if isinstance(item, str):
                model.untranslatable.append(item)
                continue
            enc = encode_paragraph(item.element)
            if not enc.text.strip():
                continue
            if enc.has_field:
                model.untranslatable.append(f"slide {item.slide_no}: paragraph with a field (kept as-is)")
                continue
            model.segments.append(Segment(
                id=item.segment_id, kind=item.kind, container=item.slide_no, shape_key=item.shape_key,
                source=enc.text, tag_ids=frozenset(tag_ids(enc.text)),
            ))
        return model
