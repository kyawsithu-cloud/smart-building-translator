"""What every check needs about one paragraph: plain source and translation, glossary hints, identifiers."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from sbt.domain.models import DocumentModel, Segment
from sbt.pipeline.tags import strip_tags
from sbt.pipeline.translator import nothing_to_translate
from sbt.protection import tokens as tok
from sbt.terminology.glossary import Glossary, Hint

_SPACE = re.compile(r"\s+")


@dataclass
class Pair:
    seg: Segment
    source: str                  # plain source text
    target: str                  # plain translation ("" = none)
    hints: tuple[Hint, ...]      # glossary entries found in the source (incl. do-not-translate)
    protected: list[str]         # identifiers that must appear unchanged
    kept: bool                   # nothing to translate (numbers, codes, names only): copied as-is

    @property
    def where(self) -> str:
        return f"{'page' if 'page' in self.seg.geometry else 'slide'} {self.seg.container}"


def norm(text: str) -> str:
    return _SPACE.sub(" ", text).strip()


def pairs(doc: DocumentModel, src: str, tgt: str, glossary: Glossary) -> list[Pair]:
    by_slide: dict[int, list[Segment]] = defaultdict(list)
    for s in doc.segments:
        by_slide[s.container].append(s)
    slide_text = {n: "\n".join(s.plain_source for s in segs) for n, segs in by_slide.items()}
    out = []
    for s in doc.segments:
        plain = s.plain_source
        hints = tuple(glossary.match(plain, src, tgt, context_text=slide_text[s.container]))
        protected = tok.protected_tokens(plain, [h.source for h in hints if h.do_not_translate])
        out.append(Pair(s, plain, strip_tags(s.translation or ""), hints, protected,
                        nothing_to_translate(plain, src, protected)))
    return out
