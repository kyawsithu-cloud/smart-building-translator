// First-start setup guide: welcome → languages → translation model (download, or copy/use a folder) → ready.
// Opens by itself when the translation model is missing; also from Models ("Run the setup guide").
import { call } from "../api.js";
import { state, show } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast } from "../ui.js";

const STEPS = ["Welcome", "Languages", "Translation model", "Ready"];
let step = 0;
let langs = null;            // Set of language codes the user works with
let target = null;           // usual target language ("" = automatic)
let withRepair = false;      // also download the repair model
let found = null;            // result of scanning a folder / USB stick
let timer = null;

const gb = (mb) => (mb < 1000 ? `${mb} MB` : `${(mb / 1024).toFixed(1)} GB`);
const name = (code) => (state.info.languages.find((l) => l.code === code) || {}).name || code;

export const setupView = {
  async render() {
    const st = await call("setup_status");
    if (langs === null) {
      target = st.settings.target_lang || "";
      langs = new Set(["en", "ja", ...(target ? [target] : [])]);
    }
    const body = [welcome, languages, model, ready][step](st);
    return el("section", { class: "view setup" },
      el("div", { class: "setup-head" },
        el("h1", {}, "Set up Smart Building Translator"),
        step < 3 ? el("a", { href: "#translate", class: "muted small", onclick: (e) => { e.preventDefault(); leave(); } }, "Set up later") : null),
      el("div", { class: "setup-steps" }, STEPS.map((label, i) =>
        el("div", { class: `setup-step ${i < step ? "done" : i === step ? "active" : ""}` },
          el("span", { class: "n" }, i < step ? icon("check") : String(i + 1)), label))),
      el("div", { class: "card setup-card" }, body));
  },
  leave() { clearInterval(timer); timer = null; },
};

function go(n) { step = n; show("setup"); }
function leave() { show("translate"); }
function nav(back, next, nextLabel = "Next", disabled = false) {
  return el("div", { class: "actions", style: "margin-top:22px" },
    back ? btn("Back", { onclick: back }) : null, el("span", { class: "spacer" }),
    next ? btn(nextLabel, { kind: "primary", disabled, onclick: next }) : null);
}

// --- 1. welcome --------------------------------------------------------------------------------------------
function welcome(st) {
  const gpu = st.hardware.gpus[0];
  const tile = (label, value, detail) => el("div", { class: "tile" }, el("div", { class: "l" }, label),
    el("div", { style: "font-weight:600;margin-top:2px" }, value), detail ? el("div", { class: "muted small" }, detail) : null);
  return [
    el("h2", {}, "Welcome"),
    el("p", {}, "This app translates PowerPoint and PDF documents — including scanned PDFs — between English, Japanese, ",
      "Chinese, Korean, Burmese, Thai, German, French and Spanish, and keeps their layout."),
    el("div", { class: "note ok" }, icon("shield"), "Everything happens on this computer. Your documents are never sent to the internet."),
    el("div", { class: "grid-3", style: "margin-top:16px" },
      tile("Processor", st.hardware.cpu, `${st.hardware.cores} threads`),
      tile("Memory", `${st.hardware.ram_gib} GB RAM`),
      tile("Graphics", gpu ? gpu.name : "No NVIDIA graphics card", gpu ? `${(gpu.vram_total_mib / 1024).toFixed(1)} GB` : "the processor will be used (slower)")),
    el("p", { class: "muted small", style: "margin-top:12px" }, `Expected speed: ${st.recommendation.expectation}`),
    el("p", {}, "Setting up takes three short steps: your languages, the translation model (about 7 GB, once), done."),
    nav(null, () => go(1), "Start"),
  ];
}

// --- 2. languages ------------------------------------------------------------------------------------------
function languages() {
  const choose = el("select", { onchange: (e) => { target = e.target.value; } },
    el("option", { value: "", selected: target === "" }, "Automatic — English ↔ Japanese, other languages → English"),
    state.info.languages.map((l) => el("option", { value: l.code, selected: target === l.code }, l.name)));
  const chips = el("div", { class: "lang-grid" }, state.info.languages.map((l) => {
    const input = el("input", { type: "checkbox", checked: langs.has(l.code) });
    input.addEventListener("change", () => { input.checked ? langs.add(l.code) : langs.delete(l.code); show("setup"); });
    return el("label", { class: `lang-chip ${langs.has(l.code) ? "on" : ""}` }, input, l.name);
  }));
  const ocr = ["ko", "th"].filter((c) => langs.has(c));
  return [
    el("h2", {}, "Your languages"),
    el("p", { class: "muted" }, "Which languages do you work with?"),
    chips,
    ocr.length ? el("div", { class: "note", style: "margin-top:12px" }, icon("info"),
      `Scanned ${ocr.map(name).join(" and ")} pages need a small extra reader (under 15 MB); it is included in the next step.`) : null,
    langs.has("my") ? el("div", { class: "note", style: "margin-top:8px" }, icon("info"),
      "Burmese: text documents are fully supported; scanned Burmese pages cannot be read.") : null,
    el("label", { class: "field", style: "margin-top:18px;max-width:520px" }, "Usually translate into", choose),
    el("p", { class: "muted small" }, "This is preselected for every document. You can still pick another language for each document before translating."),
    nav(() => go(0), () => go(2), "Next", langs.size === 0),
  ];
}

// --- 3. translation model ----------------------------------------------------------------------------------
function needed(st) {
  const items = ["engine", "hy-mt2-7b"];
  if (langs.has("ko")) items.push("ocr-ko");
  if (langs.has("th")) items.push("ocr-th");
  if (withRepair) items.push("qwen3-8b");
  return items;
}

function model(st) {
  const p = st.progress, running = p.download.status === "running" || p.copy.status === "running";
  clearInterval(timer);
  if (running) timer = setInterval(async () => {
    const now = await call("setup_progress");
    if (now.download.status !== "running" && now.copy.status !== "running") {
      clearInterval(timer); timer = null;
      const result = now.copy.status !== "idle" && now.copy.status !== "running" ? now.copy : now.download;
      if (result.status === "done") { found = null; toast(result.message); }
      show("setup");
    } else updateProgress(now);
  }, 1000);
  if (running) return progressPanel(p);

  const items = needed(st);
  const missing = items.filter((i) => !st.installed[i]);
  const ready = !st.installed.engine || !st.installed["hy-mt2-7b"] ? false : true;
  const last = [p.copy, p.download].find((x) => x.status === "failed" || x.status === "cancelled");
  const head = [
    el("h2", {}, "Translation model"),
    last ? el("div", { class: `note ${last.status === "failed" ? "err" : ""}` }, icon("alert"), last.message) : null,
  ];
  if (ready) {               // the essentials are there; readers / repair model are optional extras
    const extraMb = missing.reduce((sum, i) => sum + (st.sizes_mb[i] || 0), 0);
    return [...head,
      el("div", { class: "note ok" }, icon("check"), el("div", {}, el("strong", {}, "Installed. "),
        "The translation engine and model are ready in ", el("span", { class: "path" }, st.runtime.path))),
      el("ul", { class: "list", style: "margin-top:10px" },
        Object.entries(st.installed).filter(([, v]) => v).map(([k]) => el("li", {}, label(k)))),
      missing.length ? el("div", { class: "choice", style: "margin-top:12px" },
        el("div", { class: "choice-head" }, icon("download"), el("strong", {}, "Optional extras"),
          el("span", { class: "muted small" }, gb(extraMb))),
        el("ul", { class: "list" }, missing.map((i) => el("li", {}, `${label(i)} — ${gb(st.sizes_mb[i])}`))),
        el("div", { class: "actions" }, btn("Download extras", { icon: "download", onclick: async () => {
          try { await call("setup_download", missing); show("setup"); } catch (err) { toast(err.message, "err"); } } }),
          el("span", { class: "muted small" }, "or skip — you can add them later in Models."))) : null,
      nav(() => go(1), () => go(3))];
  }
  const total = missing.reduce((sum, i) => sum + (st.sizes_mb[i] || 0), 0);
  const free = st.runtime.free_gb;
  const tight = free != null && free < total / 1024 + 1;
  const repair = el("input", { type: "checkbox", checked: withRepair, disabled: st.installed["qwen3-8b"] });
  repair.addEventListener("change", () => { withRepair = repair.checked; show("setup"); });
  const download = el("div", { class: "choice" },
    el("div", { class: "choice-head" }, icon("download"), el("strong", {}, "Download"), el("span", { class: "muted small" }, `about ${gb(total)}`)),
    el("ul", { class: "list" }, missing.map((i) => el("li", {}, `${label(i)} — ${gb(st.sizes_mb[i])}`))),
    el("label", { class: "switch", style: "margin:8px 0" }, repair, el("div", {}, el("div", { class: "t" }, "Also get the repair model (Qwen3, 5.4 GB)"),
      el("div", { class: "d" }, "Re-translates paragraphs that still have problems. Optional; can be added later in Models."))),
    el("div", { class: "muted small" }, "Saved to ", el("span", { class: "path" }, st.runtime.path),
      free != null ? ` · ${free} GB free` : "", " · ",
      el("a", { href: "#", onclick: async (e) => { e.preventDefault(); try { await call("choose_runtime_dir"); show("setup"); } catch (err) { toast(err.message, "err"); } } }, "Change…")),
    tight ? el("div", { class: "note warn", style: "margin-top:8px" }, icon("alert"), "Not enough free space on this drive. Choose another folder (Change…).") : null,
    el("div", { class: "note", style: "margin-top:10px" }, icon("shield"),
      "From the official sources only. Every file is checked against its published fingerprint (SHA-256) and the program files are scanned by Windows Defender. This is the only time the app uses the internet."),
    el("div", { class: "actions", style: "margin-top:12px" }, btn("Download", { kind: "primary", icon: "download", disabled: tight,
      onclick: async () => { try { await call("setup_download", missing); show("setup"); } catch (err) { toast(err.message, "err"); } } })));
  const folder = el("div", { class: "choice" },
    el("div", { class: "choice-head" }, icon("folder"), el("strong", {}, "From a folder or USB stick"),
      el("span", { class: "muted small" }, "no internet needed")),
    el("p", { class: "muted small", style: "margin:6px 0 10px" }, "Already have the models — for example copied from another PC with this app? Choose that folder."),
    found ? folderResult(found) : null,
    el("div", { class: "actions" }, btn(found ? "Choose another folder…" : "Choose folder…", { icon: "folder", onclick: async () => {
      try { const r = await call("scan_models_folder"); if (r) { found = r; show("setup"); } } catch (err) { toast(err.message, "err"); } } })));
  return [...head, el("p", { class: "muted" }, "The app needs its translation engine and model once. Choose how to get them:"),
    el("div", { class: "choices" }, download, folder), nav(() => go(1), null)];
}

function label(id) {
  return { engine: "Translation engine", "hy-mt2-7b": "Translation model (Hy-MT2)", "qwen3-8b": "Repair model (Qwen3)",
           "ocr-ko": "Korean scanned-page reader", "ocr-th": "Thai scanned-page reader" }[id] || id;
}

function folderResult(f) {
  const has = (id) => f.components.includes(id);
  const line = (ok, text) => el("li", { class: ok ? "" : "muted" }, ok ? "✓ " : "✗ ", text);
  const copy = btn("Copy to this PC", { kind: f.removable ? "primary" : "", icon: "download", onclick: async () => {
    try { await call("copy_models", f.path); show("setup"); } catch (err) { toast(err.message, "err"); } } });
  const use = btn("Use it where it is", { kind: f.removable ? "" : "primary", onclick: async () => {
    try { await call("use_models_folder", f.path); found = null; toast("Models folder set"); show("setup"); } catch (err) { toast(err.message, "err"); } } });
  return el("div", { class: "found" },
    el("div", { class: "path" }, f.path),
    el("ul", { class: "list" }, line(f.engine, "translation engine"), line(has("hy-mt2-7b"), "translation model (Hy-MT2)"),
      has("qwen3-8b") ? line(true, "repair model (Qwen3)") : null,
      has("ocr-ko") ? line(true, "Korean scanned-page reader") : null, has("ocr-th") ? line(true, "Thai scanned-page reader") : null),
    f.usable ? el("div", { class: "actions", style: "margin-top:8px" }, copy, use,
      el("span", { class: "muted small" }, f.removable ? `USB stick: copy it (${f.size_gb} GB), so the app works without the stick.`
        : `On this PC: use it directly (nothing copied), or copy ${f.size_gb} GB.`))
      : el("div", { class: "note warn" }, icon("alert"), "This folder does not contain the translation engine and model. Choose the folder that contains “llama” and “models”."));
}

function progressPanel(p) {
  const copying = p.copy.status === "running";
  const s = copying ? p.copy : p.download;
  return [
    el("h2", {}, copying ? "Copying the translation model" : "Downloading the translation model"),
    el("div", { class: "bar", style: "margin:14px 0 8px" }, el("div", { id: "setup-bar", style: `width:${copying ? s.percent : s.overall}%` })),
    el("div", { id: "setup-line", class: "muted small" }, progressText(p)),
    el("ul", { id: "setup-done", class: "list", style: "margin-top:10px" }, doneList(p)),
    el("div", { class: "muted small", style: "margin-top:10px" }, "You can keep the window open and do something else meanwhile."),
    el("div", { class: "actions", style: "margin-top:16px" }, el("span", { class: "spacer" }),
      btn("Cancel", { icon: "x", onclick: async () => { await call("cancel_setup"); } })),
  ];
}

function progressText(p) {
  if (p.copy.status === "running") return `${p.copy.percent}% · ${p.copy.copied_mb} of ${p.copy.total_mb} MB · ${p.copy.file}`;
  const d = p.download;
  return `${d.overall}% of ${gb(d.total_mb)} · ${label(assetItem(d.asset))} ${d.percent}%`;
}

function assetItem(asset) {
  return { "llama-cuda": "engine", cudart: "engine" }[asset] || asset;
}

function doneList(p) {
  const names = p.copy.status === "running" ? p.copy.verified : p.download.finished;
  return [...new Set(names)].map((n) => el("li", {}, `✓ ${label(assetItem(n))} — verified`));
}

function updateProgress(p) {
  const bar = document.getElementById("setup-bar"), line = document.getElementById("setup-line"), done = document.getElementById("setup-done");
  if (!bar) return;
  bar.style.width = `${p.copy.status === "running" ? p.copy.percent : p.download.overall}%`;
  line.textContent = progressText(p);
  done.replaceChildren(...doneList(p));
}

// --- 4. ready ----------------------------------------------------------------------------------------------
function ready(st) {
  const finish = btn("Start translating", { kind: "primary big", icon: "translate", onclick: async () => {
    finish.disabled = true;
    try { state.info = await call("finish_setup", target); langs = null; step = 0; show("translate"); }
    catch (e) { toast(e.message, "err"); finish.disabled = false; }
  } });
  return [
    el("div", { class: "result-head" }, el("div", { class: "badge-big ok" }, icon("check")),
      el("div", {}, el("h2", { style: "margin:0" }, "All set"), el("div", { class: "muted small" }, "Smart Building Translator is ready to use."))),
    el("ul", { class: "list", style: "margin-top:14px" },
      el("li", {}, "Usually translate into: ", el("strong", {}, target ? name(target) : "Automatic (English ↔ Japanese)")),
      el("li", {}, "Models folder: ", el("span", { class: "path" }, st.runtime.path)),
      el("li", {}, "Runs on: ", st.hardware.gpus.length ? "the graphics card" : "the processor")),
    el("p", { class: "muted small" }, "Change these any time in Settings and Models."),
    el("div", { class: "actions", style: "margin-top:22px" }, btn("Back", { onclick: () => go(2) }), el("span", { class: "spacer" }), finish),
  ];
}
