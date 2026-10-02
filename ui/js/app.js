// App shell: navigation, theme, shared state, drag & drop.
import { call } from "./api.js";
import { hydrateIcons } from "./icons.js";
import { toast } from "./ui.js";
import { translateView } from "./views/translate.js";
import { reviewView } from "./views/review.js";
import { glossaryView } from "./views/glossary.js";
import { historyView } from "./views/history.js";
import { modelsView } from "./views/models.js";
import { settingsView } from "./views/settings.js";

const views = { translate: translateView, review: reviewView, glossary: glossaryView, history: historyView,
                models: modelsView, settings: settingsView };

// Shared state between views (one window, one translation at a time).
export const state = { info: null, file: null, job: null, result: null, reviewDirty: false };

export function applyTheme(theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function setReviewBadge(n) {
  const b = document.getElementById("review-badge");
  b.textContent = n ? String(n) : "";
  b.classList.toggle("hidden", !n);
}

let current = null;
export async function show(name) {
  name = views[name] ? name : "translate";
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === name));
  if (current && current.leave) current.leave();
  const main = document.getElementById("main");
  current = views[name];
  try {
    const node = await current.render();
    main.replaceChildren(node);
    hydrateIcons(main);
    main.scrollTop = 0;
  } catch (e) {
    toast(e.message, "err");
  }
}

// Drag & drop: the window shows an overlay; the real file path arrives from Python (window.sbtFileDropped),
// because the page itself is not allowed to see file paths.
function setupDrop() {
  const overlay = document.getElementById("drop-overlay");
  let depth = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; overlay.classList.remove("hidden"); });
  window.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; overlay.classList.add("hidden"); } });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; overlay.classList.add("hidden"); });
  window.sbtFileDropped = (path) => {
    overlay.classList.add("hidden");
    if (state.job && state.job.status === "running") { toast("Wait until the current translation has finished.", "err"); return; }
    state.file = { path, pending: true };
    show("translate");
  };
}

async function start() {
  hydrateIcons(document);
  setupDrop();
  try {
    state.info = await call("app_info");
    applyTheme(state.info.settings.theme || "system");
  } catch (e) {
    toast(`Could not start: ${e.message}`, "err");
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () =>
    applyTheme((state.info && state.info.settings.theme) || "system"));
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1) || "translate");
}

start();
