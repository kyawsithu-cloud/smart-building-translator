// Translate: choose a file → options → progress → result.
import { call } from "../api.js";
import { state, show, setReviewBadge } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast, pct, langName } from "../ui.js";

const STEP_ORDER = ["read", "load", "terms", "translate", "align", "repair", "write"];
const STEP_LABEL = { read: "Reading the document", load: "Loading the translation model", terms: "Finding recurring terms",
                     translate: "Translating", align: "Making terms consistent", repair: "Re-checking flagged paragraphs",
                     write: "Writing the translated document" };
let timer = null;

export const translateView = {
  async render() {
    const root = el("section", { class: "view" },
      el("div", {}, el("h1", {}, "Translate a document"),
        el("p", { class: "sub" }, "PowerPoint and PDF, including scanned PDFs. Your file stays on this computer.")));
    if (state.file && state.file.pending) {
      try { state.file = await call("inspect_file", state.file.path); }
      catch (e) { toast(e.message, "err"); state.file = null; }
    }
    const job = state.job;
    if (job && job.status === "running") root.append(progressCard(root));
    else if (job && job.status === "done" && state.result) root.append(resultCard(state.result));
    else {
      if (job && job.status === "failed") root.append(failedCard(job.error));
      if (job && job.status === "cancelled") root.append(el("div", { class: "note" }, icon("info"), "The translation was cancelled. Nothing was written."));
      root.append(state.file ? fileCard(state.file) : dropZone());
      if (state.file) root.append(optionsCard(state.file));
    }
    return root;
  },
  leave() { clearInterval(timer); timer = null; },
};

// --- choosing a file ------------------------------------------------------------------------------------
async function chooseFile() {
  const path = await call("choose_file");
  if (!path) return;
  try {
    state.file = await call("inspect_file", path);
    state.job = null; state.result = null;
    show("translate");
  } catch (e) { toast(e.message, "err"); }
}

function dropZone() {
  const zone = el("div", { class: "drop" },
    icon("upload", "i big-icon"),
    el("div", { class: "t" }, "Drop a PowerPoint or PDF file here"),
    el("div", { class: "muted" }, "or"),
    btn("Browse…", { kind: "primary", icon: "folder", onclick: chooseFile }),
    el("div", { class: "muted small" }, ".pptx · .pdf (text or scanned) — the original is never changed"));
  return zone;
}

function fileCard(f) {
  const lang = langName(f.detected, state.info.languages);
  const chips = el("div", { class: "chips" },
    el("span", { class: "chip" }, `${f.pages} ${f.type === "PDF" ? "page" : "slide"}${f.pages === 1 ? "" : "s"}`),
    f.paragraphs ? el("span", { class: "chip" }, `${f.paragraphs} paragraphs`) : null,
    el("span", { class: "chip" }, f.size_kb > 1024 ? `${(f.size_kb / 1024).toFixed(1)} MB` : `${f.size_kb} KB`),
    el("span", { class: "chip accent" }, `Detected: ${lang}`));
  return el("div", { class: "card" },
    el("div", { class: "file" },
      el("div", { class: `file-icon ${f.type.toLowerCase()}` }, f.type),
      el("div", { style: "flex:1;min-width:0" }, el("div", { class: "name" }, f.name), chips),
      btn("Change", { onclick: chooseFile })),
    (f.notes || []).map((n) => el("div", { class: "note", style: "margin-top:12px" }, icon("info"), n)));
}

// --- options ---------------------------------------------------------------------------------------------
function optionsCard(f) {
  const langs = state.info.languages;
  const s = state.info.settings;
  const sel = (value) => el("select", {}, langs.map((l) => el("option", { value: l.code, selected: l.code === value }, l.name)));
  const src = sel(f.detected), tgt = sel(f.target);
  const swap = btn("", { kind: "icon swap", icon: "swap", title: "Swap languages", onclick: () => {
    const a = src.value; src.value = tgt.value; tgt.value = a; } });
  const glossary = el("select", {}, state.info.glossaries.map((g) => el("option", { value: g, selected: g === s.glossary }, g)));
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
      state.job = { status: "running", stage: "read", stages_done: [], done: 0, total: 0, elapsed: 0 };
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

// --- progress ---------------------------------------------------------------------------------------------
function progressCard(root) {
  const steps = el("div", { class: "steps" });
  const bar = el("div", { class: "bar indeterminate" }, el("div"));
  const status = el("div", { class: "muted small" });
  const cancel = btn("Cancel", { icon: "x", onclick: async () => { cancel.disabled = true; await call("cancel"); } });
  const card = el("div", { class: "card" },
    el("div", { class: "card-row" }, el("h2", { style: "margin:0;flex:1" }, `Translating ${state.file ? state.file.name : ""}`), cancel),
    steps, bar, status);
  const paint = (s) => {
    steps.replaceChildren(...STEP_ORDER.filter((k) => k !== "repair" || s.stages_done.includes("repair") || s.stage === "repair")
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
      state.job = s;
      if (s.status === "running") { paint(s); return; }
      clearInterval(timer); timer = null;
      if (s.status === "done") { state.result = s.result; setReviewBadge(s.result.flagged); }
      show("translate");
    } catch (e) { toast(e.message, "err"); }
  }, 500);
  return card;
}

// --- result -----------------------------------------------------------------------------------------------
function resultCard(r) {
  const warnings = r.warnings.length > 0;
  const tile = (v, l) => el("div", { class: "tile" }, el("div", { class: "v" }, v), el("div", { class: "l" }, l));
  const lines = [
    ...r.warnings.map((w) => `${w.count} × ${w.text}`),
    ...r.not_translatable.map((u) => `${u.count} × ${u.text}`),
    ...(r.font_reduced ? [`${r.font_reduced} × text box font reduced to fit (informational)`] : []),
  ];
  const card = el("div", { class: "card" },
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
    lines.length ? el("div", { style: "margin-top:14px" }, el("div", { class: "small muted", style: "font-weight:600" }, "Details"),
      el("ul", { class: "list" }, lines.map((l) => el("li", {}, l)))) : null,
    r.notices.map((n) => el("div", { class: `note ${n.startsWith("WARNING") ? "warn" : ""}`, style: "margin-top:10px" },
      icon(n.startsWith("WARNING") ? "alert" : "info"), n.replace(/^WARNING:\s*/, ""))),
    r.flagged ? el("div", { class: "note warn", style: "margin-top:10px" }, icon("alert"),
      `${r.flagged} paragraph${r.flagged === 1 ? " needs" : "s need"} a look — they are marked in Review.`) : null,
    r.doc_terms_unresolved ? el("div", { class: "note", style: "margin-top:10px" }, icon("book"),
      `${r.doc_terms_unresolved} recurring term(s) were translated inconsistently. Choose the right translation in the term sheet, then import it into your glossary.`) : null,
    el("div", { class: "actions", style: "margin-top:18px" },
      btn("Open translated file", { kind: "primary", icon: "open", onclick: () => call("open_result", "file") }),
      btn("Open folder", { icon: "folder", onclick: () => call("open_result", "folder") }),
      btn("Review translation", { icon: "review", onclick: () => show("review") }),
      r.doc_terms ? btn("Term sheet", { icon: "book", onclick: () => call("open_result", "terms") }) : null,
      el("span", { class: "spacer" }),
      btn("Translate another", { icon: "plus", onclick: () => { state.file = null; state.job = null; state.result = null; setReviewBadge(0); show("translate"); } })));
  return card;
}

function failedCard(message) {
  return el("div", { class: "note err" }, icon("alert"),
    el("div", {}, el("strong", {}, "The translation did not complete. "), message));
}
