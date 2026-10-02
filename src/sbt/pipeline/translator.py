"""Document translation pipeline.

Pass 1  document term sheet: recurring non-glossary terms and candidate translations
Pass 2  per slide: skip → glossary (+context) → memory (exact reuse / similar examples) → engine → validate
        → retry (feedback, term injection, bare) → tag fallback
Pass 3  (doc_terms = vote) harmonise: re-translate paragraphs that deviate from the majority term translation
Pass 4  optional repair of still-flagged segments with a second engine (called separately)
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace

from sbt import languages
from sbt.domain.models import DocumentModel, Issue, Segment, SegmentKind, Severity
from sbt.engines.base import TranslationEngine, TranslationItem, TranslationRequest
from sbt.pipeline.tags import retag, strip_tags
from sbt.pipeline.validate import RETRYABLE, Problem, validate
from sbt.protection import tokens as tok
from sbt.storage.memory import TranslationMemory
from sbt.terminology import term_sheet
from sbt.terminology.glossary import Glossary, Hint, inject
from sbt.terminology.term_sheet import TermSheet

log = logging.getLogger(__name__)
BATCH = 12
_PUNCT_NUM = re.compile(r"[\d\s\W_]+")


@dataclass
class PipelineOptions:
    source_lang: str
    target_lang: str
    protect: str = "verify"            # "verify" | "mask"
    context_chars: int = 600
    doc_terms: str = "vote"            # "off" | "vote" | "hint" | "enforce" (see term_sheet.py)


@dataclass
class SegmentOutcome:
    status: str = "translated"   # translated|memory|kept|retried|retagged|simplified|failed|harmonised|repaired
    problems: list[str] = field(default_factory=list)
    score: int = 0                     # lower is better; used to compare against a repair attempt


@dataclass
class PipelineResult:
    issues: list[Issue]
    outcomes: dict[str, SegmentOutcome]
    term_checks: int = 0
    term_hits: int = 0
    token_checks: int = 0
    token_hits: int = 0
    doc_term_checks: int = 0
    doc_term_hits: int = 0
    harmonised: int = 0
    repair_tried: int = 0
    term_sheet: TermSheet | None = None


@dataclass
class _Work:
    seg: Segment
    item: TranslationItem
    protected: list[str]
    mapping: dict[str, str]
    ctx: list[str]
    previous: list[tuple[str, str]]


def _nothing_to_translate(text: str, src: str, protected: list[str]) -> bool:
    residue = text
    for t in sorted(protected, key=len, reverse=True):
        residue = residue.replace(t, " ")
    residue = _PUNCT_NUM.sub("", residue)
    script = languages.get(src).script
    return not residue or (script is not None and not script.search(residue))


class TranslationPipeline:
    def __init__(self, engine: TranslationEngine, glossary: Glossary, options: PipelineOptions,
                 memory: TranslationMemory | None = None) -> None:
        self.engine = engine
        self.glossary = glossary
        self.opt = options
        self.memory = memory
        self._work: dict[str, _Work] = {}

    # --- context ----------------------------------------------------------------------------------------
    def _context(self, segs: list[Segment], seg: Segment) -> list[str]:
        """Read-only context for one paragraph:
          heading      none (only earlier lines, passed separately as `previous`)
          other text   the nearest heading above it on the slide/page
          notes        all headings + body text of the slide

        The text being translated must NOT appear in its own context (Hy-MT2 then abbreviated "Air Handling
        Unit (AHU)" to "AHU"), and other headings must not either (a PDF page has several; Hy-MT2 then added
        the next heading to its translation)."""
        if seg.kind == SegmentKind.TITLE:
            return []
        if seg.kind != SegmentKind.NOTE:
            heading = None
            for s in segs:
                if s is seg:
                    break
                if s.kind == SegmentKind.TITLE:
                    heading = s
            return [f"Heading: {heading.plain_source}"] if heading else []
        texts = [f"Heading: {s.plain_source}" for s in segs if s.kind == SegmentKind.TITLE]
        texts += [s.plain_source for s in segs if s.kind not in (SegmentKind.TITLE, SegmentKind.NOTE)]
        ctx, size = [], 0
        for text in texts:
            if size + len(text) > self.opt.context_chars:
                break
            ctx.append(text)
            size += len(text)
        return ctx

    def _hints(self, plain: str, slide_text: str, sheet: TermSheet | None) -> tuple[Hint, ...]:
        src, tgt = self.opt.source_lang, self.opt.target_lang
        hints = self.glossary.match(plain, src, tgt, context_text=slide_text)
        if sheet is not None:
            hints += sheet.hints(plain, hints)
        return tuple(hints)

    def _checked_hints(self, hints: tuple[Hint, ...]) -> tuple[Hint, ...]:
        """Hints that validation enforces: glossary and voted terms always; hint-mode document terms only
        in 'enforce' mode."""
        return tuple(h for h in hints if h.origin in ("glossary", "consensus") or self.opt.doc_terms == "enforce")

    # --- main pass --------------------------------------------------------------------------------------
    def run(self, model: DocumentModel, progress=None) -> PipelineResult:
        src, tgt = self.opt.source_lang, self.opt.target_lang
        result = PipelineResult([], {})
        mode = self.opt.doc_terms
        if mode != "off":
            result.term_sheet = term_sheet.build(model.segments, src, tgt, self.glossary, self.engine,
                                                 contexts=3 if mode == "vote" else 1)
            log.info("Term sheet: %d candidate terms", len(result.term_sheet.all_terms))
        hint_sheet = result.term_sheet if mode in ("hint", "enforce") else None

        by_slide: dict[int, list[Segment]] = defaultdict(list)
        for s in model.segments:
            by_slide[s.container].append(s)

        done = 0
        for slide_no in sorted(by_slide):
            segs = by_slide[slide_no]
            slide_text = "\n".join(s.plain_source for s in segs)
            work: list[tuple[Segment, TranslationItem, list[str], dict[str, str]]] = []
            for s in segs:
                plain = s.plain_source
                hints = self._hints(plain, slide_text, hint_sheet)
                dnt = [h.source for h in hints if h.do_not_translate]
                protected = tok.protected_tokens(plain, dnt)
                if _nothing_to_translate(plain, src, protected):
                    s.translation = s.source
                    result.outcomes[s.id] = SegmentOutcome("kept")
                    continue
                text, mapping = (tok.mask(s.source) if self.opt.protect == "mask" else (s.source, {}))
                examples = tuple((m.source, m.target) for m in self.memory.similar(src, tgt, s.source)) \
                    if self.memory else ()
                work.append((s, TranslationItem(s.id, text, hints, _is_heading(s), examples=examples),
                             protected, mapping))

            previous: list[tuple[str, str]] = []      # this slide's finished lines, for consistency
            ordered = [w for w in work if w[0].kind != SegmentKind.NOTE] + \
                      [w for w in work if w[0].kind == SegmentKind.NOTE]
            batch: list = []
            batch_ctx: list[str] | None = None
            for w in ordered:                          # consecutive paragraphs with the same context share a batch
                ctx = self._context(segs, w[0])
                if batch and (ctx != batch_ctx or len(batch) >= BATCH):
                    self._translate_batch(batch, batch_ctx or [], previous, result)
                    batch = []
                batch.append(w)
                batch_ctx = ctx
            if batch:
                self._translate_batch(batch, batch_ctx or [], previous, result)
            done += len(segs)
            if progress:
                progress(done, len(model.segments))

        if mode == "vote" and result.term_sheet is not None:
            self._harmonise(model, result.term_sheet, result)
        self._finalise(model, result)
        return result

    def _harmonise(self, model: DocumentModel, sheet: TermSheet, result: PipelineResult) -> None:
        """Pick each term's majority in-sentence translation; re-translate only the paragraphs that deviate.
        A re-translation is kept only if it uses the term and is not worse by validation score."""
        src, tgt = self.opt.source_lang, self.opt.target_lang
        by_id = {s.id: s for s in model.segments}
        for term in sheet.all_terms:
            segs = [by_id[i] for i in term.segments if by_id[i].translation and i in self._work]
            term.target = term_sheet.vote(term, [s.translation or "" for s in segs], tgt)
            if not term.target:
                term.note = "no consistent translation found"
                continue
            for s in segs:
                if term_sheet.contains(s.translation or "", term.target, tgt):
                    continue
                w = self._work[s.id]
                hint = Hint(term.source, term.target, False, origin="consensus")
                w2 = replace(w, item=replace(w.item, hints=w.item.hints + (hint,)))
                raw = self.engine.translate(TranslationRequest(src, tgt, [w2.item], w2.ctx, w2.previous))
                out, problems, outcome = self._attempts(self.engine, w2, raw.translations.get(w2.item.id, ""))
                fatal = any(p.code in ("empty", "untranslated") for p in problems)
                if term_sheet.contains(out, term.target, tgt) and not fatal \
                        and _score(problems) <= result.outcomes[s.id].score:
                    outcome.status = "harmonised"
                    self._work[s.id] = w2
                    self._accept(w2, out, problems, outcome, result, [])
                    result.harmonised += 1

    def _translate_batch(self, batch, ctx: list[str], previous: list[tuple[str, str]],
                         result: PipelineResult) -> None:
        src, tgt = self.opt.source_lang, self.opt.target_lang
        pending: list[_Work] = []
        for s, item, protected, mapping in batch:
            w = _Work(s, item, protected, mapping, ctx, list(previous))
            self._work[s.id] = w
            hit = self.memory.exact(src, tgt, item.text) if self.memory and not mapping else None
            if hit is not None:
                out, problems = self._check(hit.target, w)
                if not any(p.code in RETRYABLE for p in problems):     # still valid with today's glossary
                    self._accept(w, out, problems, SegmentOutcome("memory"), result, previous)
                    continue
            pending.append(w)
        if not pending:
            return
        req = TranslationRequest(src, tgt, [w.item for w in pending], ctx, list(previous))
        first = self.engine.translate(req).translations
        for w in pending:
            w.previous = list(previous)
            out, problems, outcome = self._attempts(self.engine, w, first.get(w.item.id, ""))
            self._accept(w, out, problems, outcome, result, previous)

    def _attempts(self, engine: TranslationEngine, w: _Work, first_raw: str
                  ) -> tuple[str, list[Problem], SegmentOutcome]:
        """First answer → retries → tag fallback. Returns the best output found."""
        src, tgt = self.opt.source_lang, self.opt.target_lang
        s, item = w.seg, w.item
        outcome = SegmentOutcome()
        out, problems = self._check(first_raw, w)
        if any(p.code in RETRYABLE for p in problems):
            # Missing terms: put the approved terms into the source text (hints alone were ignored).
            # Other problems: tell the model what went wrong.
            outcome.status = "retried"
            terms_missing = any(p.code == "term_missing" for p in problems)
            fb = " ".join(p.feedback for p in problems if p.feedback and p.code != "term_missing")
            text = inject(item.text, self._checked_hints(item.hints)) if terms_missing else item.text
            retry_item = TranslationItem(item.id, text, item.hints, item.is_heading, fb, item.examples)
            again = engine.translate(TranslationRequest(src, tgt, [retry_item], w.ctx, w.previous)).translations
            out2, problems2 = self._check(again.get(item.id, ""), w)
            if _score(problems2) < _score(problems):
                out, problems = out2, problems2
            if any(p.code in RETRYABLE for p in problems):     # last resort: same, without any context
                bare = engine.translate(TranslationRequest(src, tgt, [retry_item])).translations
                out4, problems4 = self._check(bare.get(item.id, ""), w)
                if _score(problems4) < _score(problems):
                    out, problems = out4, problems4
        if any(p.code == "tags" for p in problems):                          # fall back: no inline tags
            plain_item = TranslationItem(item.id, strip_tags(item.text), item.hints, item.is_heading)
            plain = engine.translate(TranslationRequest(src, tgt, [plain_item], w.ctx, w.previous)).translations
            out3, problems3 = self._check(plain.get(item.id, ""), w, tags_expected=False)
            if out3.strip():
                known = {t: t for t in w.protected}
                known.update({h.source: h.target for h in item.hints})
                known.update({h.source.lower(): h.target for h in item.hints})
                retagged = retag(s.source, out3, known)
                if retagged is not None:
                    out, problems = retagged, [p for p in problems3 if p.code != "tags"]
                    outcome.status = "retagged"
                else:
                    out, problems = out3, problems3
                    outcome.status = "simplified"
        return out, problems, outcome

    def _accept(self, w: _Work, out: str, problems: list[Problem], outcome: SegmentOutcome,
                result: PipelineResult, previous: list[tuple[str, str]]) -> None:
        s = w.seg
        fatal = any(p.code in ("empty", "untranslated") for p in problems)
        s.formatting_simplified = outcome.status == "simplified"
        if fatal:
            outcome.status = "failed"
            s.translation = None
        else:
            s.translation = out
            previous.append((s.source, out))
            if self.memory and not problems and outcome.status not in ("simplified", "memory") and not w.mapping:
                self.memory.store(self.opt.source_lang, self.opt.target_lang, s.source, out,
                                  self.engine.info.model)
        outcome.problems = [p.code for p in problems]
        outcome.score = _score(problems) + (100 if fatal else 0) + (5 if s.formatting_simplified else 0)
        result.outcomes[s.id] = outcome

    # --- repair pass ------------------------------------------------------------------------------------
    def flagged(self, result: PipelineResult) -> list[str]:
        return [sid for sid, o in result.outcomes.items()
                if o.status == "failed" or any(c in RETRYABLE for c in o.problems)]

    def repair(self, model: DocumentModel, engine: TranslationEngine, result: PipelineResult) -> int:
        """Re-translate still-flagged segments with a second engine; keep whichever result scores better."""
        ids = self.flagged(result)
        result.repair_tried = len(ids)
        improved = 0
        src, tgt = self.opt.source_lang, self.opt.target_lang
        for sid in ids:
            w = self._work.get(sid)
            if w is None:
                continue
            before = result.outcomes[sid]
            first = engine.translate(TranslationRequest(src, tgt, [w.item], w.ctx, w.previous)).translations
            out, problems, outcome = self._attempts(engine, w, first.get(w.item.id, ""))
            candidate = _score(problems) + (100 if any(p.code in ("empty", "untranslated") for p in problems)
                                            else 0) + (5 if outcome.status == "simplified" else 0)
            if candidate < before.score:
                outcome.status = "repaired"
                self._accept(w, out, problems, outcome, result, [])
                improved += 1
        self._finalise(model, result)
        return improved

    # --- checks and metrics -----------------------------------------------------------------------------
    def _check(self, raw: str, w: _Work, tags_expected: bool = True) -> tuple[str, list[Problem]]:
        s = w.seg
        out = tok.tidy(s.source, raw.strip(), self.opt.target_lang)
        if not s.tag_ids:            # models sometimes invent formatting tags: drop them
            out = strip_tags(out)
        out = tok.restore_parentheses(s.plain_source, out, w.protected, self.opt.target_lang)
        placeholders = list(w.mapping)
        pre_problems = [Problem("placeholders", f"Keep the placeholder {ph} exactly once.")
                        for ph in placeholders if out.count(ph) != 1]
        out = tok.unmask(out, w.mapping)
        source = s.source if tags_expected else strip_tags(s.source)
        problems = pre_problems + validate(source, out, w.protected, self._checked_hints(w.item.hints),
                                           self.opt.source_lang, self.opt.target_lang)
        return out, problems

    def _finalise(self, model: DocumentModel, result: PipelineResult) -> None:
        """(Re)compute metrics and issues from the final state of every segment."""
        result.issues = []
        result.term_checks = result.term_hits = result.token_checks = result.token_hits = 0
        result.doc_term_checks = result.doc_term_hits = 0
        for s in model.segments:
            w = self._work.get(s.id)
            o = result.outcomes.get(s.id)
            if w is None or o is None:
                continue
            for code in o.problems:
                sev = Severity.ERROR if code in ("empty", "untranslated") else Severity.WARNING
                result.issues.append(Issue(code, sev, s.id, f"slide {s.container}: {code}"))
            if s.translation is None:      # left in the original language; counted in translated_pct instead
                continue
            plain = strip_tags(s.translation)
            result.token_checks += len(w.protected)
            result.token_hits += sum(t in plain for t in w.protected)
            for h in w.item.hints:
                if h.do_not_translate or h.origin != "glossary":
                    continue
                result.term_checks += 1
                result.term_hits += h.target.lower() in plain.lower()
        if result.term_sheet is not None:          # document-term consistency, same measure for every mode
            by_id = {s.id: s for s in model.segments}
            for term in result.term_sheet.terms:
                for sid in term.segments:
                    if by_id[sid].translation:
                        result.doc_term_checks += 1
                        result.doc_term_hits += term_sheet.contains(by_id[sid].translation or "", term.target,
                                                                    self.opt.target_lang)
        result.issues.extend(self._consistency(model))
        if self.memory:
            self.memory.commit()

    def _consistency(self, model: DocumentModel) -> list[Issue]:
        """Same glossary source term → same target everywhere. Reports terms whose usage varies."""
        usage: dict[str, Counter[bool]] = defaultdict(Counter)
        for s in model.segments:
            w = self._work.get(s.id)
            if not s.translation or w is None:
                continue
            for h in w.item.hints:
                if not h.do_not_translate and h.origin == "glossary":
                    usage[h.source.lower()][h.target.lower() in strip_tags(s.translation).lower()] += 1
        inconsistent = [k for k, c in usage.items() if c[True] and c[False]]
        if not inconsistent:
            return []
        return [Issue("term_inconsistent", Severity.WARNING, None,
                      f"{len(inconsistent)} glossary term(s) translated inconsistently")]


def _is_heading(s: Segment) -> bool:
    if s.kind == SegmentKind.TITLE:
        return True
    if s.kind == SegmentKind.NOTE:
        return False
    text = s.plain_source.strip()
    return not re.search(r"[.。!?！？]$", text) and len(text) < 90


def _score(problems: list[Problem]) -> int:
    return sum(10 if p.code in RETRYABLE else 1 for p in problems)
