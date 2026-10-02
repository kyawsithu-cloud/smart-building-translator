"""Document term sheet: recurring terms that are not in the glossary.

Mining finds phrases that occur in several paragraphs (e.g. "chilled water plant"). Each is translated in up to
three of its contexts to collect candidate translations. How they are used depends on the doc_terms mode:

  hint / enforce   the first candidate is given to the model as a term hint everywhere (enforce = validated)
  vote             paragraphs are translated normally; afterwards the candidate the model actually used most
                   often in full sentences wins, and only the paragraphs that deviate are re-translated

Measured on the consistency deck (eval/results/PHASE2_RESULTS.md): isolated term translations are much worse
than in-sentence translations for EN→JA, so 'hint' locked in wrong terms; 'vote' avoids that.

The sheet is written next to the output as `<name>.terms.csv` in glossary format for review and import.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sbt import languages
from sbt.domain.models import Segment
from sbt.engines.base import TranslationEngine, TranslationItem, TranslationRequest
from sbt.protection import tokens as tok
from sbt.terminology.glossary import Glossary, Hint, Term, term_regex

MAX_TERMS = 40
_EN_STOP = set("""a an the and or of to in on for with by from at as is are be was were this that these those it its
into over under via per than then also not no all any each every more most less such can may will must should
our your their his her we you they i up out about between during after before when where which who what how""".split())
_EN_EDGE_STOP = _EN_STOP | {"and", "of", "for", "with"}
_CHUNK_SPLIT = re.compile(r"[,.;:!?()\[\]{}\"“”'’/|•→–—]|\s-\s|\n")
_EN_WORD = re.compile(r"^[A-Za-z][A-Za-z\-]*$")
_JA_RUN = re.compile(r"[\u30a1-\u30f4\u30fc\uff66-\uff9f\u4e00-\u9faf\u3005]+")
_KATAKANA_ONLY = re.compile(r"^[\u30a1-\u30f4\u30fc\uff66-\uff9f]+$")
_SCRIPT_CHUNK = re.compile(r"[\u30a1-\u30f4\u30fc\uff66-\uff9f]+|[\u4e00-\u9faf\u3005]+")
_LATIN = ("en", "de", "fr", "es")


@dataclass
class DocTerm:
    source: str
    segments: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)     # paragraphs containing the term, longest first
    candidates: list[str] = field(default_factory=list)   # translations of the term in its contexts
    target: str = ""                                      # chosen translation ("" = none chosen)
    note: str = ""

    @property
    def occurrences(self) -> int:
        return len(self.segments)


class TermSheet:
    def __init__(self, src: str, tgt: str, terms: list[DocTerm]) -> None:
        self.src, self.tgt = src, tgt
        self.all_terms = terms

    @property
    def terms(self) -> list[DocTerm]:
        return [t for t in self.all_terms if t.target]

    def hints(self, text: str, taken: list[Hint]) -> list[Hint]:
        """Document hints for `text`, skipping anything already covered by a glossary hint."""
        covered = " ".join(h.source.lower() for h in taken)
        out: list[Hint] = []
        for t in sorted(self.terms, key=lambda t: -len(t.source)):
            if t.source.lower() in covered or not term_regex(t.source).search(text):
                continue
            if any(t.source.lower() in h.source.lower() for h in out):
                continue
            out.append(Hint(t.source, t.target, False, origin="document"))
        return out

    def as_terms(self) -> list[Term]:
        """Glossary rows for review. Unresolved terms are included with their first candidate, marked."""
        rows = []
        for t in self.all_terms:
            if t.target:
                note = f"{t.occurrences} paragraphs; review before importing"
            elif t.candidates:
                note = (f"UNRESOLVED ({t.occurrences} paragraphs, translated inconsistently); candidates: "
                        f"{' / '.join(t.candidates)} — correct the target before importing")
            else:
                continue
            rows.append(Term(t.source, t.target or t.candidates[0], self.src, self.tgt, "document", note,
                             False, "normal"))
        return rows


def _norm(text: str, tgt: str) -> str:
    """Latin: case-insensitive. Japanese/Chinese/Thai/Burmese: spaces are optional, so ignore them."""
    text = re.sub(r"</?g\d+>", "", text)
    return text.lower() if tgt in _LATIN else re.sub(r"\s+", "", text)


def contains(translation: str, target: str, tgt: str) -> bool:
    return _norm(target, tgt) in _norm(translation, tgt)


# --- mining -------------------------------------------------------------------------------------------------
def _mask_known(text: str, glossary: Glossary, src: str, tgt: str) -> str:
    """Cut glossary terms and protected identifiers out of the text so they are not mined again."""
    for h in glossary.match(text, src, tgt):
        text = term_regex(h.source).sub(" | ", text)
    for t in tok.protected_tokens(text, []):
        text = text.replace(t, " | ")
    return text


def _en_candidates(text: str) -> set[str]:
    found: set[str] = set()
    for chunk in _CHUNK_SPLIT.split(text):
        words = chunk.split()
        for n in range(2, 6):
            for i in range(len(words) - n + 1):
                gram = words[i:i + n]
                if not all(_EN_WORD.match(w) for w in gram):
                    continue
                low = [w.lower() for w in gram]
                if low[0] in _EN_EDGE_STOP or low[-1] in _EN_EDGE_STOP:
                    continue
                if sum(w not in _EN_STOP for w in low) < 2 or not any(len(w) >= 4 for w in low):
                    continue
                found.add(" ".join(low))
    return found


def _ja_candidates(text: str) -> set[str]:
    """Japanese writes compounds without spaces (冷水プラント効率), so split each katakana/kanji run where the
    script changes and use 1–4 neighbouring pieces: 冷水 | プラント | 効率 → 冷水プラント, プラント効率, …"""
    found: set[str] = set()
    for run in _JA_RUN.findall(text):
        chunks = _SCRIPT_CHUNK.findall(run)
        for n in range(1, 5):
            for i in range(len(chunks) - n + 1):
                cand = "".join(chunks[i:i + n])
                if 3 <= len(cand) <= 15 and not (_KATAKANA_ONLY.match(cand) and len(cand) < 5):
                    found.add(cand)
    return found


def mine(segments: list[Segment], src: str, tgt: str, glossary: Glossary) -> list[DocTerm]:
    terms: dict[str, DocTerm] = {}
    for s in segments:
        plain = s.plain_source
        masked = _mask_known(plain, glossary, src, tgt)
        cands = _ja_candidates(masked) if src in ("ja", "zh") else _en_candidates(masked)
        for c in cands:
            term = terms.setdefault(c, DocTerm(c))
            term.segments.add(s.id)
            term.examples.append(plain)
    recurring = [t for t in terms.values() if t.occurrences >= 2]
    # Keep maximal phrases: drop a phrase contained in a longer one that occurs in the same paragraphs.
    kept: list[DocTerm] = []
    for t in sorted(recurring, key=lambda t: -len(t.source)):
        if any(t.source in k.source and t.segments <= k.segments for k in kept):
            continue
        t.examples = sorted(set(t.examples), key=len, reverse=True)
        kept.append(t)
    kept.sort(key=lambda t: (-t.occurrences, -len(t.source)))
    return kept[:MAX_TERMS]


# --- candidate translations ---------------------------------------------------------------------------------
def build(segments: list[Segment], src: str, tgt: str, glossary: Glossary, engine: TranslationEngine,
          contexts: int = 1) -> TermSheet:
    """Mine terms and translate each in up to `contexts` of its paragraphs. target = first candidate."""
    terms = mine(segments, src, tgt, glossary)
    jobs: dict[str, list[tuple[int, TranslationItem]]] = {}
    for i, t in enumerate(terms):
        for k, example in enumerate(t.examples[:contexts]):
            jobs.setdefault(example, []).append((i, TranslationItem(f"t{i}_{k}", t.source, is_heading=True)))
    for example, items in jobs.items():
        result = engine.translate(TranslationRequest(src, tgt, [it for _, it in items], [example])).translations
        for i, item in items:
            cand = _clean(result.get(item.id, ""), terms[i].source, tgt)
            if cand and all(_norm(cand, tgt) != _norm(c, tgt) for c in terms[i].candidates):
                terms[i].candidates.append(cand)
    for t in terms:
        t.target = t.candidates[0] if t.candidates else ""
    return TermSheet(src, tgt, terms)


def vote(term: DocTerm, translations: list[str], tgt: str) -> str:
    """The candidate used most often in the in-sentence translations, if it is a clear majority."""
    if len(translations) < 2 or not term.candidates:
        return ""
    support = {c: sum(contains(tr, c, tgt) for tr in translations) for c in term.candidates}
    best = max(support, key=lambda c: (support[c], len(c)))
    return best if support[best] >= 2 and support[best] * 2 > len(translations) else ""


def _clean(raw: str, source: str, tgt: str) -> str:
    """Accept only a plausible short term translation; otherwise leave it out."""
    out = raw.strip().strip("。.、,「」\"'").strip()
    if not out or "\n" in out or len(out) > 4 * len(source) + 10:
        return ""
    script = languages.get(tgt).script
    if tgt not in _LATIN and script is not None and not script.search(out):
        return ""
    if tgt in _LATIN and re.search(r"[぀-ヿ一-鿿]", out):
        return ""
    return out
