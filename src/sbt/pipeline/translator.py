"""Document translation pipeline: skip → glossary → context → cache → engine → validate → retry → fallback."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from sbt import languages
from sbt.domain.models import DocumentModel, Issue, Segment, SegmentKind, Severity
from sbt.engines.base import TranslationEngine, TranslationItem, TranslationRequest
from sbt.engines.prompts import PROMPT_VERSION
from sbt.pipeline.tags import retag, strip_tags
from sbt.pipeline.validate import RETRYABLE, Problem, validate
from sbt.protection import tokens as tok
from sbt.terminology.glossary import Glossary, Hint, inject

log = logging.getLogger(__name__)
BATCH = 12
_PUNCT_NUM = re.compile(r"[\d\s\W_]+")


@dataclass
class PipelineOptions:
    source_lang: str
    target_lang: str
    protect: str = "verify"            # "verify" | "mask"
    context_chars: int = 600
    cache_path: Path | None = None


@dataclass
class SegmentOutcome:
    status: str = "translated"         # translated | kept | retried | simplified | failed
    problems: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    issues: list[Issue]
    outcomes: dict[str, SegmentOutcome]
    term_checks: int = 0
    term_hits: int = 0
    token_checks: int = 0
    token_hits: int = 0


class _Cache:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data: dict[str, str] = {}
        if path and path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")


def _nothing_to_translate(text: str, src: str, protected: list[str]) -> bool:
    residue = text
    for t in sorted(protected, key=len, reverse=True):
        residue = residue.replace(t, " ")
    residue = _PUNCT_NUM.sub("", residue)
    script = languages.get(src).script
    return not residue or (script is not None and not script.search(residue))


class TranslationPipeline:
    def __init__(self, engine: TranslationEngine, glossary: Glossary, options: PipelineOptions) -> None:
        self.engine = engine
        self.glossary = glossary
        self.opt = options
        self.cache = _Cache(options.cache_path)

    def _dnt(self, text: str) -> list[str]:
        return [h.source for h in self.glossary.match(text, self.opt.source_lang, self.opt.target_lang)
                if h.do_not_translate]

    def _key(self, item: TranslationItem, context: list[str]) -> str:
        raw = json.dumps([self.engine.info.id, PROMPT_VERSION, self.opt.source_lang, self.opt.target_lang,
                          item.text, [h.__dict__ for h in item.hints], item.is_heading, context],
                         ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _context(self, segs: list[Segment], for_notes: bool) -> list[str]:
        """Slide title for slide text; title + slide body for speaker notes.

        The text being translated must NOT appear in its own context: in testing, Hy-MT2 then abbreviated
        "Air Handling Unit (AHU)" to "AHU". Earlier lines of the slide are passed separately as `previous`.
        """
        title = [f"Slide title: {s.plain_source}" for s in segs if s.kind == SegmentKind.TITLE]
        others = [s.plain_source for s in segs if s.kind != SegmentKind.TITLE and s.kind != SegmentKind.NOTE]
        ctx, size = [], 0
        for text in title + (others if for_notes else []):
            if size + len(text) > self.opt.context_chars:
                break
            ctx.append(text)
            size += len(text)
        return ctx

    def run(self, model: DocumentModel, progress=None) -> PipelineResult:
        src, tgt = self.opt.source_lang, self.opt.target_lang
        result = PipelineResult([], {})
        by_slide: dict[int, list[Segment]] = defaultdict(list)
        for s in model.segments:
            by_slide[s.container].append(s)

        done = 0
        for slide_no in sorted(by_slide):
            segs = by_slide[slide_no]
            work: list[tuple[Segment, TranslationItem, list[str], dict[str, str]]] = []
            for s in segs:
                plain = s.plain_source
                protected = tok.protected_tokens(plain, self._dnt(plain))
                if _nothing_to_translate(plain, src, protected):
                    s.translation = s.source
                    result.outcomes[s.id] = SegmentOutcome("kept")
                    continue
                text, mapping = (tok.mask(s.source) if self.opt.protect == "mask" else (s.source, {}))
                hints = tuple(h for h in self.glossary.match(plain, src, tgt))
                item = TranslationItem(s.id, text, hints, is_heading=_is_heading(s))
                work.append((s, item, protected, mapping))

            previous: list[tuple[str, str]] = []      # this slide's finished lines, for consistency
            for note in (False, True):
                part = [w for w in work if (w[0].kind == SegmentKind.NOTE) == note]
                ctx = self._context(segs, note)
                for i in range(0, len(part), BATCH):
                    self._translate_batch(part[i:i + BATCH], ctx, previous, result)
            done += len(segs)
            if progress:
                progress(done, len(model.segments))
            self.cache.save()

        result.issues.extend(self._consistency(model))
        return result

    def _translate_batch(self, batch, ctx: list[str], previous: list[tuple[str, str]],
                         result: PipelineResult) -> None:
        src, tgt = self.opt.source_lang, self.opt.target_lang
        pending = []
        for s, item, protected, mapping in batch:
            cached = self.cache.data.get(self._key(item, ctx))
            if cached is not None:
                s.translation = cached
                previous.append((s.source, cached))
                result.outcomes[s.id] = SegmentOutcome("translated")
                self._count(result, s.source, cached, protected, item.hints)
            else:
                pending.append((s, item, protected, mapping))
        if not pending:
            return

        req = TranslationRequest(src, tgt, [p[1] for p in pending], ctx, list(previous))
        first = self.engine.translate(req).translations
        for s, item, protected, mapping in pending:
            outcome = SegmentOutcome()
            out, problems = self._check(first.get(item.id, ""), s, item, protected, mapping)
            if any(p.code in RETRYABLE for p in problems):
                # Retry. Missing terms: put the approved terms into the source text (hints alone were
                # ignored). Other problems: tell the model what went wrong.
                outcome.status = "retried"
                terms_missing = any(p.code == "term_missing" for p in problems)
                fb = " ".join(p.feedback for p in problems if p.feedback and p.code != "term_missing")
                text = inject(item.text, item.hints) if terms_missing else item.text
                retry_item = TranslationItem(item.id, text, item.hints, item.is_heading, fb)
                again = self.engine.translate(TranslationRequest(src, tgt, [retry_item], ctx,
                                                                 list(previous))).translations
                out2, problems2 = self._check(again.get(item.id, ""), s, item, protected, mapping)
                if _score(problems2) < _score(problems):
                    out, problems = out2, problems2
                if any(p.code in RETRYABLE for p in problems):     # last resort: same, without any context
                    bare = self.engine.translate(TranslationRequest(src, tgt, [retry_item])).translations
                    out4, problems4 = self._check(bare.get(item.id, ""), s, item, protected, mapping)
                    if _score(problems4) < _score(problems):
                        out, problems = out4, problems4
            if any(p.code == "tags" for p in problems):                          # fall back: no inline tags
                plain_item = TranslationItem(item.id, strip_tags(item.text), item.hints, item.is_heading)
                plain = self.engine.translate(TranslationRequest(src, tgt, [plain_item], ctx,
                                                                 list(previous))).translations
                out3, problems3 = self._check(plain.get(item.id, ""), s, plain_item, protected, mapping,
                                              tags_expected=False)
                if out3.strip():
                    known = {t: t for t in protected}
                    known.update({h.source: h.target for h in item.hints})
                    known.update({h.source.lower(): h.target for h in item.hints})
                    retagged = retag(s.source, out3, known)
                    if retagged is not None:
                        out, problems = retagged, [p for p in problems3 if p.code != "tags"]
                        outcome.status = "retagged"
                    else:
                        out, problems = out3, problems3
                        s.formatting_simplified = True
                        outcome.status = "simplified"
            fatal = [p for p in problems if p.code in ("empty", "untranslated")]
            if fatal:
                outcome.status = "failed"
                s.translation = None
            else:
                s.translation = out
                previous.append((s.source, out))
                if outcome.status != "simplified" and not problems:
                    self.cache.data[self._key(item, ctx)] = out
            outcome.problems = [p.code for p in problems]
            result.outcomes[s.id] = outcome
            self._count(result, s.source, out, protected, item.hints)
            for p in problems:
                sev = Severity.ERROR if p.code in ("empty", "untranslated") else Severity.WARNING
                result.issues.append(Issue(p.code, sev, s.id, f"slide {s.container}: {p.code} ({p.count})"))

    def _check(self, raw: str, s: Segment, item: TranslationItem, protected: list[str],
               mapping: dict[str, str], tags_expected: bool = True) -> tuple[str, list[Problem]]:
        out = tok.tidy(s.source, raw.strip(), self.opt.target_lang)
        if not s.tag_ids:            # models sometimes invent formatting tags: drop them
            out = strip_tags(out)
        out = tok.restore_parentheses(s.plain_source, out, protected, self.opt.target_lang)
        placeholders = list(mapping)
        pre_problems = [] if not placeholders else [
            Problem("placeholders", f"Keep the placeholder {ph} exactly once.")
            for ph in placeholders if out.count(ph) != 1]
        out = tok.unmask(out, mapping)
        source = s.source if tags_expected else strip_tags(s.source)
        problems = pre_problems + validate(source, out, protected, item.hints,
                                           self.opt.source_lang, self.opt.target_lang)
        return out, problems

    @staticmethod
    def _count(result: PipelineResult, source: str, out: str, protected: list[str],
               hints: tuple[Hint, ...]) -> None:
        plain = strip_tags(out)
        result.token_checks += len(protected)
        result.token_hits += sum(t in plain for t in protected)
        real = [h for h in hints if not h.do_not_translate]
        result.term_checks += len(real)
        result.term_hits += sum(h.target.lower() in plain.lower() for h in real)

    def _consistency(self, model: DocumentModel) -> list[Issue]:
        """Same glossary source term → same target everywhere. Reports terms whose usage varies."""
        issues: list[Issue] = []
        usage: dict[str, Counter[bool]] = defaultdict(Counter)
        for s in model.segments:
            if not s.translation:
                continue
            for h in self.glossary.match(s.plain_source, self.opt.source_lang, self.opt.target_lang):
                if not h.do_not_translate:
                    usage[h.source.lower()][h.target.lower() in strip_tags(s.translation).lower()] += 1
        inconsistent = [k for k, c in usage.items() if c[True] and c[False]]
        if inconsistent:
            issues.append(Issue("term_inconsistent", Severity.WARNING, None,
                                f"{len(inconsistent)} glossary term(s) translated inconsistently"))
        return issues


def _is_heading(s: Segment) -> bool:
    if s.kind == SegmentKind.TITLE:
        return True
    if s.kind == SegmentKind.NOTE:
        return False
    text = s.plain_source.strip()
    return not re.search(r"[.。!?！？]$", text) and len(text) < 90


def _score(problems: list[Problem]) -> int:
    return sum(10 if p.code in RETRYABLE else 1 for p in problems)
