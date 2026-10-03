// Translate: choose a file → options → progress → result with quality checks.
// Check: choose an original and a translation made elsewhere → progress → quality checks.
import { call } from "../api.js";
import { state, show, setReviewBadge } from "../app.js";
import { icon } from "../icons.js";
import { hasProblems, qualitySummary } from "../quality.js";
import { el, btn, toast, pct, langName } from "../ui.js";

const STEP_ORDER = ["read", "load", "terms", "translate", "align", "repair", "write", "check"];
const CHECK_STEPS = ["read", "load", "terms", "check"];
const STEP_LABEL = { read: "Reading the document", load: "Loading the translation model", terms: "Finding recurring terms",
                     translate: "Translating", align: "Making terms consistent", repair: "Re-checking flagged paragraphs",
                     write: "Writing the translated document", check: "Checking quality" };
let timer = null;

const openReview = (category) => { state.reviewCategory = category; show("review"); };

export const translateView = {
  async render() {
    const checking = state.mode === "check";
    const root = el("section", { class: "view" },
      el("div", {}, el("h1", {}, checking ? "Check a translation" : "Translate a document"),
        el("p", { class: "sub" }, checking
          ? "Compare a translation made elsewhere with its original: terminology, missing text, identifiers, layout."
          : "PowerPoint and PDF, including scanned PDFs. Your file stays on this computer.")));
    await inspectPending();
    const job = state.job;
    if (job && job.status === "running") root.append(progressCard());
    else if (job && job.status === "done" && state.result) {
      root.append(state.result.kind === "check" ? checkResultCard(state.result) : resultCard(state.result));
    } else {
      if (job && job.status === "failed") root.append(failedCard(job.error));
      if (job && job.status === "cancelled") root.append(el("div", { class: "note" }, icon("info"), "Cancelled. Nothing was written."));
      if (checking) root.append(...checkSetup());
      else {
        root.append(state.file ? fileCard(state.file) : dropZone());
        if (state.file) root.append(optionsCard(state.file));
      }
    }
    return root;
  },
  leave() { clearInterval(timer); timer = null; },
};

async function inspectPending() {
  try {
    if (state.file && state.file.pending) state.file = await call("inspect_file", state.file.path);
    for (const slot of ["original", "translation"]) {
      const f = state.check[slot];
      if (f && f.pending) state.check[slot] = await call("inspect_file", f.path);
    }
  } catch (e) {
    toast(e.message, "err");
    if (state.file && state.file.pending) state.file = null;
    for (const slot of ["original", "translation"]) if (state.check[slot] && state.check[slot].pending) state.check[slot] = null;
  }
}

function setMode(mode) {
  state.mode = mode; state.job = null; state.result = null; setReviewBadge(0);
  show("translate");
}

// --- choosing a file ------------------------------------------------------------------------------------
async function chooseFile(slot) {
  const path = await call("choose_file");
  if (!path) return;
  try {
    const info = await call("inspect_file", path);
    if (slot) state.check[slot] = info; else state.file = info;
    state.job = null; state.result = null;
    show("translate");
  } catch (e) { toast(e.message, "err"); }
}

function dropZone() {
  return el("div", {},
    el("div", { class: "drop" },
      icon("upload", "i big-icon"),
      el("div", { class: "t" }, "Drop a PowerPoint or PDF file here"),
      el("div", { class: "muted" }, "or"),
      btn("Browse…", { kind: "primary", icon: "folder", onclick: () => chooseFile() }),
      el("div", { class: "muted small" }, ".pptx · .pdf (text or scanned) — the original is never changed")),
    el("div", { class: "mode-link" }, icon("checkfile"), "Already have a translation? ",
      el("a", { href: "#translate", onclick: (e) => { e.preventDefault(); setMode("check"); } }, "Check it against the original")));
}

function chips(f) {
  return el("div", { class: "chips" },
    el("span", { class: "chip" }, `${f.pages} ${f.type === "PDF" ? "page" : "slide"}${f.pages === 1 ? "" : "s"}`),
    f.paragraphs ? el("span", { class: "chip" }, `${f.paragraphs} paragraphs`) : null,
    el("span", { class: "chip" }, f.size_kb > 1024 ? `${(f.size_kb / 1024).toFixed(1)} MB` : `${f.size_kb} KB`),
    el("span", { class: "chip accent" }, `Detected: ${langName(f.detected, state.info.languages)}`));
}

function fileCard(f, onChange = () => chooseFile(), label = null) {
  return el("div", { class: "card" },
    label ? el("div", { class: "small muted", style: "margin-bottom:6px;font-weight:600" }, label) : null,
    el("div", { class: "file" },
      el("div", { class: `file-icon ${f.type.toLowerCase()}` }, f.type),
      el("div", { style: "flex:1;min-width:0" }, el("div", { class: "name" }, f.name), chips(f)),
      btn("Change", { onclick: onChange })),
    (f.notes || []).map((n) => el("div", { class: "note", style: "margin-top:12px" }, icon("info"), n)));
}

function langSelect(value) {
  return el("select", {}, state.info.languages.map((l) => el("option", { value: l.code, selected: l.code === value }, l.name)));
}

function glossarySelect() {
  return el("select", {}, state.info.glossaries.map((g) => el("option", { value: g, selected: g === state.info.settings.glossary }, g)));
}

// --- translate options -----------------------------------------------------------------------------------
function optionsCard(f) {
  const s = state.info.settings;
  const src = langSelect(f.detected), tgt = langSelect(f.target);
  const swap = btn("", { kind: "icon swap", icon: "swap", title: "Swap languages", onclick: () => {
    const a = src.value; src.value = tgt.value; tgt.value = a; } });
  const glossary = glossarySelect();
  const ocr = el("input", { type: "checkbox", checked: true });
  const memory = el("input", { type: "checkbox", checked: s.use_memory });
  const mode = el("div", { class: "seg" },
    el("button", { class: "on", type: "button" }, icon("shield"), "Offline"),
    el("button", { type: "button", disabled: true, title: "Not available in this version" }, icon("globe"), "Online"));
  const go = btn("Translate", { kind: "primary big", icon: "translate", onclick: async () => {
    if (src.value === tgt.value) { toast("Source and target language are the same.", "err"); return; }
    go.disabled = true;
    try {
      await call("start_translation", { path: f.path, source: src.value, target: tgt.value, glossary: glossary.value,
                                        ocr: ocr.checked, memory: memory.checked });
      state.job = { status: "running", kind: "translation", stage: "read", stages_done: [], done: 0, total: 0, elapsed: 0 };
      state.result = null;
      show("translate");
    } catch (e) { toast(e.message, "err"); go.disabled = false; }
  } });
  return el("div", { class: "card" },
    el("div", { class: "options" },
      el("label", { class: "field" }, "From", src), swap,
      el("label", { class: "field" }, "To", tgt),
      el("label", { class: "field" }, "Glossary", glossary)),
    el("div", { class: "mode-row", style: "margin-top:16px" },
      el("div", { class: "field-v" }, el("span", { class: "label" }, "Mode"), mode),
      el("div", { class: "muted small", style: "max-width:520px" },
        "Offline: the document is translated by the model on this computer. Nothing is sent to the internet.")),
    el("details", { style: "margin-top:14px" }, el("summary", {}, "Options"),
      el("div", { style: "display:flex;flex-direction:column;gap:12px;margin-top:12px" },
        el("label", { class: "switch" }, ocr, el("div", {}, el("div", { class: "t" }, "Read scanned pages and text in pictures (OCR)"),
          el("div", { class: "d" }, "Scanned PDF pages are translated; text inside pictures is reported."))),
        el("label", { class: "switch" }, memory, el("div", {}, el("div", { class: "t" }, "Use translation memory"),
          el("div", { class: "d" }, "Reuse earlier translations and remember this one (stored only on this PC)."))))),
    el("div", { class: "actions", style: "margin-top:18px" }, el("span", { class: "spacer" }), go));
}

// --- check setup -------------------------------------------------------------------------------------------
function slotCard(slot, label, hint) {
  const f = state.check[slot];
  if (f) return fileCard(f, () => chooseFile(slot), label);
  return el("div", { class: "card slot" },
    el("div", { class: "small muted", style: "font-weight:600" }, label),
    el("div", { class: "slot-body" }, icon("file", "i"), el("div", { class: "muted", style: "flex:1" }, hint),
      btn("Browse…", { icon: "folder", onclick: () => chooseFile(slot) })));
}

function checkSetup() {
  const { original, translation } = state.check;
  const out = [
    slotCard("original", "Original", "The document that was translated (drop it here or browse)"),
    slotCard("translation", "Translation", "Its translation, made elsewhere (same file type)"),
  ];
  if (original && translation) {
    const src = langSelect(original.detected), tgt = langSelect(translation.detected);
    const glossary = glossarySelect();
    const modelOk = state.info.model_installed && state.info.engine_installed;
    const useModel = el("input", { type: "checkbox", checked: modelOk, disabled: !modelOk });
    const go = btn("Check translation", { kind: "primary big", icon: "checkfile", onclick: async () => {
      if (src.value === tgt.value) { toast("The original and the translation are in the same language.", "err"); return; }
      go.disabled = true;
      try {
        await call("start_check", { original: original.path, translation: translation.path, source: src.value,
                                    target: tgt.value, glossary: glossary.value, use_model: useModel.checked });
        state.job = { status: "running", kind: "check", use_model: useModel.checked, stage: "read", stages_done: [], done: 0, total: 0, elapsed: 0 };
        state.result = null;
        show("translate");
      } catch (e) { toast(e.message, "err"); go.disabled = false; }
    } });
    out.push(el("div", { class: "card" },
      el("div", { class: "options" },
        el("label", { class: "field" }, "Original language", src), el("span"),
        el("label", { class: "field" }, "Translation language", tgt),
        el("label", { class: "field" }, "Glossary", glossary)),
      el("label", { class: "switch", style: "margin-top:16px" }, useModel, el("div", {},
        el("div", { class: "t" }, "Compare recurring terms with the translation model"),
        el("div", { class: "d" }, modelOk ? "More thorough terminology check (about a minute longer). Runs on this PC."
          : "Install the translation model in Models to use this. Glossary and identifier checks run without it."))),
      el("div", { class: "actions", style: "margin-top:18px" }, el("span", { class: "spacer" }), go)));
  }
  out.push(el("div", { class: "mode-link" }, icon("translate"),
    el("a", { href: "#translate", onclick: (e) => { e.preventDefault(); setMode("translate"); } }, "Back to translating a document")));
  return out;
}

// --- progress ---------------------------------------------------------------------------------------------
function progressCard() {
  const isCheck = state.job.kind === "check";
  const steps = el("div", { class: "steps" });
  const bar = el("div", { class: "bar indeterminate" }, el("div"));
  const status = el("div", { class: "muted small" });
  const cancel = btn("Cancel", { icon: "x", onclick: async () => { cancel.disabled = true; await call("cancel"); } });
  const name = isCheck ? (state.check.translation || {}).name : (state.file || {}).name;
  const card = el("div", { class: "card" },
    el("div", { class: "card-row" }, el("h2", { style: "margin:0;flex:1" }, `${isCheck ? "Checking" : "Translating"} ${name || ""}`), cancel),
    steps, bar, status);
  const order = isCheck ? CHECK_STEPS.filter((k) => state.job.use_model || (k !== "load" && k !== "terms")) : STEP_ORDER;
  const paint = (s) => {
    steps.replaceChildren(...order.filter((k) => k !== "repair" || s.stages_done.includes("repair") || s.stage === "repair")
      .map((k) => {
        const done = s.stages_done.includes(k), active = s.stage === k;
        const extra = k === "translate" && (active || done) && s.total ? `${s.done} / ${s.total} paragraphs` : "";
        return el("div", { class: `step ${done ? "done" : active ? "active" : ""}` },
          el("div", { class: "dot" }, done ? icon("check") : ""), el("div", {}, STEP_LABEL[k]), el("div", { class: "muted small" }, extra));
      }));
    const translating = s.stage === "translate" && s.total;
    bar.classList.toggle("indeterminate", !translating);
    bar.firstChild.style.width = translating ? `${Math.round((100 * s.done) / s.total)}%` : "";
    status.textContent = `${s.stage_label || "Starting"}… · ${Math.round(s.elapsed || 0)} s`;
  };
  paint(state.job);
  clearInterval(timer);
  timer = setInterval(async () => {
    try {
      const s = await call("job_status");
      state.job = { ...state.job, ...s };
      if (s.status === "running") { paint(state.job); return; }
      clearInterval(timer); timer = null;
      if (s.status === "done") { state.result = s.result; setReviewBadge(s.result.flagged); }
      show("translate");
    } catch (e) { toast(e.message, "err"); }
  }, 500);
  return card;
}

// --- results ----------------------------------------------------------------------------------------------
function notesBlock(r) {
  return [
    ...(r.notices || []).map((n) => el("div", { class: `note ${n.startsWith("WARNING") ? "warn" : ""}`, style: "margin-top:10px" },
      icon(n.startsWith("WARNING") ? "alert" : "info"), n.replace(/^WARNING:\s*/, ""))),
  ];
}

function resultCard(r) {
  const warnings = hasProblems(r.quality);
  const tile = (v, l) => el("div", { class: "tile" }, el("div", { class: "v" }, v), el("div", { class: "l" }, l));
  return el("div", { class: "card" },
    el("div", { class: "result-head" },
      el("div", { class: `badge-big ${warnings ? "warn" : "ok"}` }, icon(warnings ? "alert" : "check")),
      el("div", {}, el("h2", { style: "margin:0" }, warnings ? "Translation completed with warnings" : "Translation completed"),
        el("div", { class: "muted small" }, `${langName(r.source, state.info.languages)} → ${langName(r.target, state.info.languages)} · ${r.segments} paragraphs · ${Math.round(r.seconds)} s`))),
    el("div", { class: "grid-2", style: "margin-top:16px" },
      el("div", {}, el("div", { class: "small muted" }, "Original"), el("div", { class: "path" }, r.input)),
      el("div", {}, el("div", { class: "small muted" }, "Translated"), el("div", { class: "path" }, r.output))),
    el("div", { class: "grid-4", style: "margin-top:16px" },
      tile(pct(r.translated_pct), "Text translated"), tile(pct(r.checks.identifiers), "Identifiers kept"),
      tile(pct(r.checks.glossary), "Glossary terms used"), tile(pct(r.checks.formatting), "Formatting kept")),
    el("div", { class: "small muted", style: "margin-top:18px;font-weight:600" }, "Quality checks"),
    qualitySummary(r.quality, openReview),
    notesBlock(r),
    r.doc_terms_unresolved ? el("div", { class: "note", style: "margin-top:10px" }, icon("book"),
      `${r.doc_terms_unresolved} recurring term(s) were translated inconsistently. Choose the right translation in the term sheet, then import it into your glossary.`) : null,
    el("div", { class: "actions", style: "margin-top:18px" },
      btn("Open translated file", { kind: "primary", icon: "open", onclick: () => call("open_result", "file") }),
      btn("Open folder", { icon: "folder", onclick: () => call("open_result", "folder") }),
      btn("Review translation", { icon: "review", onclick: () => show("review") }),
      r.doc_terms ? btn("Term sheet", { icon: "book", onclick: () => call("open_result", "terms") }) : null,
      el("span", { class: "spacer" }),
      btn("Translate another", { icon: "plus", onclick: () => { state.file = null; setMode("translate"); } })));
}

function checkResultCard(r) {
  const warnings = hasProblems(r.quality);
  const unmatched = r.segments - r.matched;
  return el("div", { class: "card" },
    el("div", { class: "result-head" },
      el("div", { class: `badge-big ${warnings ? "warn" : "ok"}` }, icon(warnings ? "alert" : "check")),
      el("div", {}, el("h2", { style: "margin:0" }, warnings ? "Check completed: some points need a look" : "Check completed: no problems found"),
        el("div", { class: "muted small" }, `${langName(r.source, state.info.languages)} → ${langName(r.target, state.info.languages)} · ${r.matched} of ${r.segments} paragraphs matched · ${Math.round(r.seconds)} s`))),
    el("div", { class: "grid-2", style: "margin-top:16px" },
      el("div", {}, el("div", { class: "small muted" }, "Original"), el("div", { class: "path" }, r.input)),
      el("div", {}, el("div", { class: "small muted" }, "Translation checked"), el("div", { class: "path" }, r.output))),
    el("div", { class: "small muted", style: "margin-top:18px;font-weight:600" }, "Quality checks"),
    qualitySummary(r.quality, openReview),
    unmatched ? el("div", { class: "note warn", style: "margin-top:10px" }, icon("alert"),
      `${unmatched} paragraph(s) of the original were not found in the translation at the same place; they are listed as not translated.`) : null,
    r.term_note ? el("div", { class: "note", style: "margin-top:10px" }, icon("info"), r.term_note) : null,
    notesBlock(r),
    el("div", { class: "actions", style: "margin-top:18px" },
      btn("Review findings", { kind: "primary", icon: "review", onclick: () => show("review") }),
      btn("Export checks", { icon: "download", onclick: async () => {
        try { const p = await call("export_checks"); if (p) toast(`Saved: ${p}`); } catch (e) { toast(e.message, "err"); } } }),
      btn("Open translation", { icon: "open", onclick: () => call("open_result", "file") }),
      el("span", { class: "spacer" }),
      btn("Check another", { icon: "plus", onclick: () => { state.check = { original: null, translation: null }; setMode("check"); } })));
}

function failedCard(message) {
  return el("div", { class: "note err" }, icon("alert"),
    el("div", {}, el("strong", {}, "It did not complete. "), message));
}
