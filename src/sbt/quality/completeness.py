"""Missing or partial translation: paragraphs left in the original language, words left untranslated, likely
omissions (translation much shorter than this document's usual ratio), content that cannot be translated."""
from __future__ import annotations

import re
import statistics

from sbt import languages
from sbt.domain.models import DocumentModel, Severity
from sbt.pipeline.validate import validate
from sbt.quality.context import Pair, norm
from sbt.quality.findings import Finding

LATIN = {"en", "de", "fr", "es"}
# English words that do not exist in German, French or Spanish: two of them in such a translation are leftovers.
_EN_ONLY = {"the", "and", "with", "is", "are", "this", "that", "for", "from", "which", "will", "be", "by", "to",
            "these", "those", "into", "their", "its", "our", "your", "should", "can", "of"}
# Lowercase words that are units or notation, not English text.
_NOTATION = {"lux", "ppm", "rpm", "sec", "min", "max", "bar", "psi", "mph", "kpa", "mpa", "khz", "mhz", "ghz",
             "kbps", "mbps", "gbps", "dpi", "ips", "fps", "www", "http", "https", "html", "json", "xml", "csv",
             "pdf", "pptx", "xlsx", "docx", "exe", "dll", "ini", "cfg", "log", "png", "jpg", "jpeg", "svg"}
_LOWER_WORD = re.compile(r"(?<![A-Za-z0-9_\-./@])[a-z]{3,}(?:-[a-z]+)*(?![A-Za-z0-9_\-@])")
_ANY_WORD = re.compile(r"[A-Za-z]+")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)|[。！？]")
_WHERE = re.compile(r"^(slide|page) (\d+)")
_NOT_WORDING = re.compile(r"[\W\d_]+")
_SOURCE_END = re.compile(r"[.!?。！？]$")
_TARGET_END = {"my": r"[။.!?]", "ja": r"[。！？.!?]", "zh": r"[。！？.!?]", "ko": r"[.!?。]"}
# A translation that stops on a word or mark that needs a continuation was cut off ("Occupancy sensor and").
_DANGLING = {
    "en": r"\b(and|or|of|the|with|for|to|a|an|in|on|by|from|via|as)$",
    "de": r"\b(und|oder|der|die|das|des|mit|für|zu|von|im|in|auf)$",
    "fr": r"\b(et|ou|de|des|du|la|le|les|avec|pour|à|en|sur|par)$",
    "es": r"\b(y|o|de|del|la|el|los|las|con|para|a|en|por)$",
    "ja": r"([、，,：:（(]|および|及び|ならびに)$",
    "zh": r"([、，,：:（(]|和|及|以及|与)$",
}


def _residue(p: Pair) -> str:
    """The translation without identifiers and do-not-translate terms."""
    text = p.target
    for t in sorted(p.protected, key=len, reverse=True):
        text = text.replace(t, " ")
    for h in p.hints:
        if h.do_not_translate or h.target == h.source:
            text = re.sub(re.escape(h.target), " ", text, flags=re.IGNORECASE)
    return text


def _content(text: str, protected: list[str]) -> int:
    """Length of the wording itself: identifiers, digits, punctuation and spaces do not count (they are
    copied unchanged, so they make short translations of identifier-heavy paragraphs look longer)."""
    for t in sorted(protected, key=len, reverse=True):
        text = text.replace(t, "")
    return len(_NOT_WORDING.sub("", text))


def _cut_off(p: Pair, tgt: str) -> bool:
    """The source paragraph ends a sentence but the translation stops without one (model stopped early).
    Thai is skipped: it does not end sentences with punctuation."""
    target = p.target.strip()
    dangling = _DANGLING.get(tgt)
    if dangling and re.search(dangling, target, re.IGNORECASE) and not re.search(dangling, p.source.strip(),
                                                                                     re.IGNORECASE):
        return True
    if tgt == "th" or not _SOURCE_END.search(p.source.strip()):
        return False
    return not re.search(_TARGET_END.get(tgt, r"[.!?]") + r"[)）」』\"'\s]*$", target)


def _sentences(text: str) -> int:
    t = text.strip()
    if not t:
        return 0
    ends = len(_SENTENCE_END.findall(t))
    return ends if _SENTENCE_END.search(t[-1]) else ends + 1


def _leftovers(p: Pair, src: str, tgt: str) -> list[str]:
    """Words or characters of the source language still in the translation."""
    residue = _residue(p)
    if tgt not in LATIN:                       # e.g. EN→JA: lowercase English words copied from the source
        source_words = {w.lower() for w in _ANY_WORD.findall(p.source)}
        words = [w for w in _LOWER_WORD.findall(residue)
                 if w in source_words and w not in _NOTATION and len(w.replace("-", "")) >= 4
                 and not re.search(rf"[A-Z][\w/]*\s+{w}\s+[A-Z]", p.target)]   # part of a name: MQTT over TLS
        return list(dict.fromkeys(words))
    if src not in LATIN:                       # e.g. JA→EN: Japanese characters left
        script = languages.get(src).script
        return list(dict.fromkeys(m.group(0) for m in re.finditer(rf"(?:{script.pattern})+", residue))) \
            if script is not None else []
    if tgt != "en" and src == "en":            # EN→DE/FR/ES: English function words
        words = [w for w in _ANY_WORD.findall(residue.lower()) if w in _EN_ONLY]
        return list(dict.fromkeys(words)) if len(words) >= 2 else []
    return []


def _not_translated(p: Pair, src: str, tgt: str) -> bool:
    if not p.target.strip():
        return True
    if norm(p.target).casefold() == norm(p.source).casefold():
        return True
    residue = _residue(p)
    tgt_script = languages.get(tgt).script
    if tgt not in LATIN and tgt_script is not None:
        return not tgt_script.search(residue)
    src_script = languages.get(src).script
    if src not in LATIN and src_script is not None:       # JA→EN: mostly Japanese characters left
        letters = [c for c in residue if not c.isspace() and not c.isdigit()]
        return bool(letters) and sum(bool(src_script.match(c)) for c in letters) > 0.5 * len(letters)
    return False


def check(pairs: list[Pair], doc: DocumentModel, src: str, tgt: str) -> list[Finding]:
    found: list[Finding] = []
    active = [p for p in pairs if not p.kept and p.seg.translation is not None]
    missing = [p for p in pairs if not p.kept and p.seg.translation is None]
    for p in missing:
        found.append(Finding("completeness", "not_translated", Severity.ERROR,
                             f"{p.where}: paragraph not translated", [p.seg.id], [p.seg.container]))

    ratios = [_content(p.target, p.protected) / _content(p.source, p.protected) for p in active
              if _content(p.source, p.protected) >= 15 and p.target.strip()]
    typical = statistics.median(ratios) if len(ratios) >= 5 else None

    for p in active:
        one = ([p.seg.id], [p.seg.container])
        if _not_translated(p, src, tgt):
            found.append(Finding("completeness", "not_translated", Severity.ERROR,
                                 f"{p.where}: paragraph not translated", *one))
            continue
        left = _leftovers(p, src, tgt)
        if left:
            found.append(Finding("completeness", "partly_translated", Severity.WARNING,
                                 f"{p.where}: {len(left)} word(s) left in the original language", *one,
                                 detail={"left": left}))
        tagged = "<g" in (p.seg.translation or "") and bool(p.seg.tag_ids)
        for prob in validate(p.seg.source if tagged else p.source, p.seg.translation if tagged else p.target,
                             p.protected, (), src, tgt):
            if prob.code == "foreign_script":
                found.append(Finding("completeness", "foreign_script", Severity.WARNING,
                                     f"{p.where}: characters from another language", *one))
            elif prob.code == "added_text":
                found.append(Finding("completeness", "added_text", Severity.WARNING,
                                     f"{p.where}: translation has extra lines (text may have been added)", *one))
        if _cut_off(p, tgt):
            found.append(Finding("completeness", "possible_omission", Severity.WARNING,
                                 f"{p.where}: translation ends mid-sentence (part may be missing)", *one,
                                 detail={"cut_off": True}))
            continue
        size = _content(p.source, p.protected)
        if typical and size >= 20:
            ratio = _content(p.target, p.protected) / size
            fewer = _sentences(p.target) < _sentences(p.source)
            # Calibrated on the clean test translations: long paragraphs never fell below 0.6 of the document's
            # usual ratio unless something was missing; headings compress legitimately (Operation and
            # Maintenance → 運用・保守, 0.36).
            limit = 0.58 if size >= 40 else 0.33
            if ratio < limit * typical or (fewer and _sentences(p.source) >= 2 and ratio < 0.8 * typical):
                found.append(Finding("completeness", "possible_omission", Severity.WARNING,
                                     f"{p.where}: translation shorter than expected (part may be missing)",
                                     *one, detail={"ratio": round(ratio / typical, 2)}))

    for note in doc.untranslatable:
        m = _WHERE.match(note)
        picture = "picture" in note
        found.append(Finding("completeness", "picture_text" if picture else "not_translatable",
                             Severity.WARNING if picture else Severity.INFO, note, [],
                             [int(m.group(2))] if m else []))
    return found
