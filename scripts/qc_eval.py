"""Quality-control evaluation: does each check find the errors it is meant to find, and how often does it raise
a false alarm on a correct translation?

1. Clean outputs: the checks run on finished translations of the public test documents. Every finding is
   listed for manual review (true problem or false alarm).
     calibration  Phase 2 + 3 outputs (thresholds were tuned on these)
     held-out     Phase 1 outputs of three different models (not looked at while tuning)
2. Seeded errors: known errors are injected into correct translations, one at a time, and we count how many
   the checks catch on the paragraph concerned.
3. Overflow: every text box of translated decks (as written, and with some texts made longer) is measured by
   the installed PowerPoint (scripts/measure_text.ps1); its layout is the truth the overflow warning is
   compared with.

    python scripts/qc_eval.py            → eval/results/phase5/qc_eval.json, qc_eval.md, clean_findings.md
"""
from __future__ import annotations

import copy
import csv
import json
import random
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

from qc_common import ROOT, load_run

from sbt import formats, quality
from sbt.domain.models import DocumentModel
from sbt.pipeline.tags import strip_tags
from sbt.protection import tokens as tok
from sbt.quality.context import pairs
from sbt.storage import db
from sbt.storage.glossary_repo import GlossaryRepo
from sbt.terminology.glossary import Glossary, term_regex
from sbt.terminology.term_sheet import DocTerm, TermSheet

OUT = ROOT / "eval" / "results" / "phase5"
RUN = re.compile(r"^(?P<name>.+)_(?P<src>[a-z]{2})-(?P<tgt>[a-z]{2})_(vote|verify)$")
PER_TYPE = 6          # injected errors per document and error type (fewer if the document has fewer candidates)
RENDER_TRIALS = 3     # for the slower error types that write a file
LATIN = {"en", "de", "fr", "es"}
# Realistic wrong-but-plausible wordings for terminology errors (fallback: the source term left in English).
ALTERNATIVES = {"ビル管理システム": "建物管理システム", "冷凍機": "チラー", "空調機": "エアハンドリングユニット",
                "警報": "アラーム", "設定値": "セットポイント", "ゲートウェイ": "ゲートウエイ", "冷水": "チルド水",
                "Building Management System": "Building Control System", "chiller": "refrigerator",
                "setpoint": "set value", "alarm": "alert"}


def glossary() -> Glossary:
    conn = db.connect(Path(tempfile.mkdtemp()) / "qc.db")
    repo = GlossaryRepo(conn)
    repo.ensure("smart-building")
    return repo.load("smart-building")


def runs(folder: str) -> list[dict[str, object]]:
    out = []
    for review in sorted((ROOT / folder).glob("*.review.csv")):
        run = review.name[: -len(".review.csv")]
        m = RUN.match(run)
        if not m:
            continue
        ext = ".pdf" if (ROOT / folder / f"{run}.pdf").exists() else ".pptx"
        original = ROOT / "eval" / "testset" / f"{m['name']}{ext}"
        if original.exists():
            out.append({"run": run, "folder": folder, "src": m["src"], "tgt": m["tgt"], "original": original,
                        "output": ROOT / folder / f"{run}{ext}", "review": review,
                        "terms": ROOT / folder / f"{run}.terms.csv"})
    return out


def load(r: dict[str, object]) -> DocumentModel:
    doc = load_run(r["original"], r["review"], r["src"])  # type: ignore[arg-type]
    # Paragraph ids that changed since an older run cannot be matched: leave them out rather than call them
    # untranslated.
    doc.segments = [s for s in doc.segments if s.translation is not None]
    return doc


def sheet_from_csv(r: dict[str, object], doc: DocumentModel) -> TermSheet | None:
    path: Path = r["terms"]  # type: ignore[assignment]
    if not path.exists():
        return None
    terms = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if "UNRESOLVED" in row["notes"]:
                continue
            rx = term_regex(row["source_term"])
            ids = {s.id for s in doc.segments if rx.search(s.plain_source)}
            if len(ids) >= 2:
                terms.append(DocTerm(row["source_term"], ids, [], [row["target_term"]], row["target_term"]))
    return TermSheet(r["src"], r["tgt"], terms)  # type: ignore[arg-type]


# --- 1. clean outputs ----------------------------------------------------------------------------------------
def clean(g: Glossary, folders: list[str], label: str, lines: list[str]) -> dict[str, object]:
    paragraphs, findings = 0, Counter()
    lines.append(f"\n## {label}\n")
    for r in [r for f in folders for r in runs(f)]:
        doc = load(r)
        rep = quality.check(doc, r["src"], r["tgt"], g, sheet=sheet_from_csv(r, doc),  # type: ignore[arg-type]
                            output=r["output"], original=r["original"])  # type: ignore[arg-type]
        found = [f for f in rep.findings if f.severity.value != "info"]
        paragraphs += sum(1 for s in doc.segments if s.translation is not None)
        findings.update(f.code for f in found)
        lines.append(f"\n### {r['folder'].split('/')[-1]}/{r['run']} ({len(doc.segments)} paragraphs): "  # type: ignore[union-attr]
                     f"{len(found)} finding(s)\n")
        by_id = {s.id: s for s in doc.segments}
        for f in found:
            lines.append(f"- [{f.severity.value}] {f.code}: {f.describe()}")
            for sid in f.segments[:2]:
                s = by_id[sid]
                lines.append(f"  - source: {s.plain_source[:140]}")
                lines.append(f"  - translation: {strip_tags(s.translation or '')[:140]}")
    return {"paragraphs": paragraphs, "findings": sum(findings.values()), "by_code": dict(findings)}


# --- 2. seeded errors ---------------------------------------------------------------------------------------
_EN_WORDS = re.compile(r"\b[a-z]{4,}\b")
_SENT = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")      # between sentences, not inside 192.168.1.100


def _replace_number(text: str, rng: random.Random) -> str | None:
    nums = [m for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text) if len(m.group(0).replace(",", "").replace(".", "")) >= 2]
    if not nums:
        return None
    m = rng.choice(nums)
    digits = m.group(0)
    changed = digits[::-1] if digits[::-1] != digits else digits[:-1] + str((int(digits[-1]) + 3) % 10)
    return text[: m.start()] + changed + text[m.end():]


def _mutate_token(t: str) -> str:
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}.*", t):
        head, last = t.rsplit(".", 1)
        return f"{head}.{last[:-1] or '1'}"                   # 192.168.1.100 → 192.168.1.10
    i = next((k for k in range(len(t) - 1, -1, -1) if t[k].isalnum()), len(t) - 1)
    c = t[i]
    repl = str((int(c) + 1) % 10) if c.isdigit() else ("x" if c != "x" else "y")
    return t[:i] + repl + t[i + 1:]


def mutations(doc: DocumentModel, g: Glossary, src: str, tgt: str, sheet: TermSheet | None,
              rng: random.Random) -> dict[str, list[tuple[str, str, set[str]]]]:
    """error type → [(segment id, mutated translation, codes that should report it)]"""
    ps = [p for p in pairs(doc, src, tgt, g) if not p.kept and p.target.strip() and "<g" not in (p.seg.translation or "")]
    out: dict[str, list[tuple[str, str, set[str]]]] = defaultdict(list)
    for p in ps:
        sid, t = p.seg.id, p.seg.translation or ""
        out["untranslated paragraph"].append((sid, p.source, {"not_translated"}))
        if tgt not in LATIN:
            words = [w for w in _EN_WORDS.findall(p.source) if w not in ("with", "from", "that", "this")]
            if len(words) >= 2:
                out["words left untranslated"].append((sid, t + " " + " ".join(words[-2:]), {"partly_translated"}))
        elif src not in LATIN:
            chunk = re.search(r"[぀-ヿ一-鿿]{3,}", p.source)
            if chunk:
                out["words left untranslated"].append((sid, t.replace(" ", f" {chunk.group(0)} ", 1), {"partly_translated"}))
        sentences = [x for x in _SENT.split(t) if x.strip()]
        if len(sentences) >= 2:
            out["sentence dropped"].append((sid, "".join(sentences[:-1]).strip(), {"possible_omission"}))
        elif len(t) >= 40:
            out["sentence dropped"].append((sid, t[: int(len(t) * 0.45)], {"possible_omission"}))
        opaque = [x for x in p.protected if tok.OPAQUE_RE.fullmatch(x) and x in t]
        if opaque:
            x = rng.choice(opaque)
            out["identifier changed"].append((sid, t.replace(x, _mutate_token(x)), {"token_changed", "token_missing"}))
        acronyms = [x for x in p.protected if not tok.OPAQUE_RE.fullmatch(x) and x in t and x.isupper()]
        if acronyms:
            x = rng.choice(acronyms)
            out["acronym dropped"].append((sid, t.replace(x, ""), {"token_missing", "token_changed"}))
        rest = t
        for x in p.protected:
            rest = rest.replace(x, "")
        if tok.significant_numbers(rest):
            changed = _replace_number(rest, rng)
            if changed:
                # apply to the full text: replace the first differing number occurrence
                out["number changed"].append((sid, _replace_number_in(t, rest, changed), {"number_changed"}))
        for unit, new in (("°C", "°F"), ("℃", "°F"), ("kWh", "MWh"), ("MWh", "kWh"), ("kW", "MW"), ("%", " ")):
            if re.search(rf"\d\s?{re.escape(unit)}", t):
                out["unit changed"].append((sid, re.sub(rf"(\d\s?){re.escape(unit)}", rf"\g<1>{new}", t, count=1),
                                            {"number_changed"}))
                break
        for h in p.hints:
            if h.do_not_translate or h.origin != "glossary" or h.target not in t:
                continue
            alt = ALTERNATIVES.get(h.target, h.source if h.source != h.target else None)
            if alt:
                wrong = re.sub(re.escape(h.target), alt, t, flags=re.IGNORECASE)     # every occurrence
                out["glossary term replaced"].append((sid, wrong, {"glossary_term"}))
                break
    if sheet is not None:
        by_id = {p.seg.id: p for p in ps}
        for term in sheet.terms:
            for sid in sorted(term.segments):
                p = by_id.get(sid)
                if p is not None and term.target in (p.seg.translation or ""):
                    alt = ALTERNATIVES.get(term.target, term.source)
                    out["recurring term worded differently"].append(
                        (sid, (p.seg.translation or "").replace(term.target, alt), {"term_variants"}))
                    break
    groups: dict[str, list] = defaultdict(list)  # type: ignore[type-arg]
    for p in ps:
        groups[p.source.strip().casefold()].append(p)
    for group in groups.values():
        if len(group) >= 2:
            p = group[-1]
            extra = "（参考）" if tgt not in LATIN else " (see above)"
            out["repeated text translated differently"].append((p.seg.id, (p.seg.translation or "") + extra,
                                                                 {"same_source_differs"}))
    for trials in out.values():
        rng.shuffle(trials)
        del trials[PER_TYPE:]
    return out


def _replace_number_in(full: str, rest: str, changed_rest: str) -> str:
    """Apply the number change found in `rest` (text without identifiers) to the full translation."""
    a = re.findall(r"\d[\d,]*(?:\.\d+)?", rest)
    b = re.findall(r"\d[\d,]*(?:\.\d+)?", changed_rest)
    for old, new in zip(a, b):
        if old != new:
            return re.sub(rf"(?<![\d.]){re.escape(old)}(?![\d])", new, full, count=1)
    return full


def detected(report: quality.QcReport, sid: str, codes: set[str]) -> bool:
    return any(f.code in codes and sid in f.segments for f in report.findings)


def seeded(g: Glossary, folders: list[str], rng: random.Random) -> dict[str, dict[str, int]]:
    tally: dict[str, dict[str, int]] = defaultdict(lambda: {"injected": 0, "detected": 0, "flagged": 0})
    missed: list[str] = []
    tmp = Path(tempfile.mkdtemp())
    for r in [r for f in folders for r in runs(f)]:
        base = load(r)
        sheet = sheet_from_csv(r, base)
        src, tgt = r["src"], r["tgt"]
        # Paragraphs the checks already flag in the correct translation say nothing about an injected error.
        before = quality.check(base, src, tgt, g, sheet=sheet).flagged_segments()  # type: ignore[arg-type]
        for kind, trials in mutations(base, g, src, tgt, sheet, rng).items():  # type: ignore[arg-type]
            for sid, text, codes in trials:
                if sid in before:
                    continue
                doc = copy.deepcopy(base)
                next(s for s in doc.segments if s.id == sid).translation = text
                rep = quality.check(doc, src, tgt, g, sheet=sheet)  # type: ignore[arg-type]
                tally[kind]["injected"] += 1
                tally[kind]["flagged"] += sid in rep.flagged_segments()     # the reviewer is pointed at it
                if detected(rep, sid, codes):
                    tally[kind]["detected"] += 1
                else:
                    missed.append(f"{kind} | {r['run']} | {sid} | {text[:90]}")
        # Errors that need the file written: a paragraph the writer did not write, and text too long for its box.
        original: Path = r["original"]  # type: ignore[assignment]
        candidates = [s for s in base.segments if s.translation and strip_tags(s.translation) != s.plain_source]
        for s in rng.sample(candidates, min(RENDER_TRIALS, len(candidates))):
            render_doc = copy.deepcopy(base)
            next(x for x in render_doc.segments if x.id == s.id).translation = None      # writer skips it
            out = tmp / f"{r['run']}_nw{original.suffix}"
            formats.renderer_for(original, src, tgt, 0.8).render(render_doc, out)  # type: ignore[arg-type]
            rep = quality.check(base, src, tgt, g, output=out, original=original)  # type: ignore[arg-type]
            tally["paragraph not written to the file"]["injected"] += 1
            tally["paragraph not written to the file"]["flagged"] += s.id in rep.flagged_segments()
            if detected(rep, s.id, {"not_written", "original_left"}):
                tally["paragraph not written to the file"]["detected"] += 1
            else:
                missed.append(f"not written | {r['run']} | {s.id}")
    (OUT / "missed.md").write_text("# Seeded errors not detected\n\n" + "\n".join(f"- {m}" for m in missed) + "\n",
                                   encoding="utf-8")
    return dict(tally)


def overflow(g: Glossary, folders: list[str], rng: random.Random) -> dict[str, object]:
    """Overflow warnings compared with PowerPoint's own layout of every text box."""
    import subprocess
    folder = Path(tempfile.mkdtemp(prefix="sbt_overflow_"))
    predicted: dict[tuple[str, int, int], str] = {}        # (file, slide, shape id) → overflow | font_reduced
    for r in [r for f in folders for r in runs(f)]:
        original: Path = r["original"]  # type: ignore[assignment]
        if original.suffix.lower() != ".pptx":
            continue
        base = load(r)
        boxes = [s for s in base.segments if s.translation and s.kind.value in ("body", "title")
                 and re.match(r"^s\d+/\d+/p\d+$", s.id)]
        variants = [("as-written", base)]
        for factor in (2, 3, 5):
            doc = copy.deepcopy(base)
            for s in rng.sample(boxes, min(4, len(boxes))):
                seg = next(x for x in doc.segments if x.id == s.id)
                seg.translation = " ".join([strip_tags(seg.translation or "")] * factor)
            variants.append((f"x{factor}", doc))
        for label, doc in variants:
            name = f"{Path(str(r['folder'])).parts[-2]}_{r['run']}_{label}.pptx"   # phase2/phase3 share run names
            issues = formats.renderer_for(original, r["src"], r["tgt"], 0.8).render(doc, folder / name)  # type: ignore[arg-type]
            for i in issues:
                m = re.match(r"^s(\d+)/(?:.*/)?(\d+)$", i.segment_id or "")
                if m and i.code in ("overflow", "overflow_inherited", "box_grows", "font_reduced"):
                    predicted[(name, int(m.group(1)), int(m.group(2)))] = i.code
    proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "scripts" / "measure_text.ps1"), "-Folder", str(folder)],
                          capture_output=True, text=True, timeout=1800, check=False)
    rows = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    cm = Counter()
    for row in rows:
        truth = row["text"] > row["box"] + 2.0                    # PowerPoint's layout, after its own auto-fit
        said = predicted.get((row["file"], row["slide"], row["shape"])) in ("overflow", "overflow_inherited", "box_grows")
        cm["tp" if truth and said else "fn" if truth else "fp" if said else "tn"] += 1
    return {"boxes": len(rows), **cm, "files": len({r["file"] for r in rows})}


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f} %" if b else "n/a"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    g = glossary()
    t0 = time.time()
    lines = ["# Quality checks on clean translations", "",
             "Every warning/error raised on finished translations of the public test documents, for manual review."]
    calibration = clean(g, ["eval/results/phase3/hy-mt2-7b", "eval/results/phase2/hy-mt2-7b"], "Calibration set (Phase 2 + 3)", lines)
    heldout = clean(g, [f"eval/results/phase1/{m}" for m in ("hy-mt2-7b", "qwen3-8b", "cat-translate-7b")],
                    "Held-out set (Phase 1, three models)", lines)
    (OUT / "clean_findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    tally = seeded(g, ["eval/results/phase3/hy-mt2-7b", "eval/results/phase2/hy-mt2-7b"], random.Random(5))
    of = overflow(g, ["eval/results/phase3/hy-mt2-7b", "eval/results/phase2/hy-mt2-7b"], random.Random(7))
    result = {"calibration": calibration, "heldout": heldout, "seeded": tally, "overflow": of,
              "seconds": round(time.time() - t0, 1)}
    (OUT / "qc_eval.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = ["| Injected error | Injected | Found by the intended check | Paragraph flagged by any check |",
          "|---|---|---|---|"]
    for kind, v in sorted(tally.items()):
        md.append(f"| {kind} | {v['injected']} | {v['detected']} ({_pct(v['detected'], v['injected'])}) | "
                  f"{v['flagged']} ({_pct(v['flagged'], v['injected'])}) |")
    total_i = sum(v["injected"] for v in tally.values())
    total_d = sum(v["detected"] for v in tally.values())
    total_f = sum(v["flagged"] for v in tally.values())
    md.append(f"| **all** | **{total_i}** | **{total_d} ({_pct(total_d, total_i)})** | "
              f"**{total_f} ({_pct(total_f, total_i)})** |")
    md += ["", "| Clean translations | Paragraphs | Warnings/errors | per 100 paragraphs |", "|---|---|---|---|"]
    for label, c in (("calibration (Phase 2 + 3)", calibration), ("held-out (Phase 1, 3 models)", heldout)):
        md.append(f"| {label} | {c['paragraphs']} | {c['findings']} | "
                  f"{100 * c['findings'] / c['paragraphs']:.1f} |")  # type: ignore[operator]
    tp, fp, fn = (int(of.get(k, 0)) for k in ("tp", "fp", "fn"))  # type: ignore[call-overload]
    md += ["", ("| Overflow warning vs PowerPoint layout | Text boxes | Overflowing (PowerPoint) | "
               "Warned and overflowing | Missed | False warnings |"), "|---|---|---|---|---|---|",
           f"| {of['files']} decks | {of['boxes']} | {tp + fn} | {tp} | {fn} | {fp} |"]
    (OUT / "qc_eval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\n{result['seconds']} s · details: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
