// History: recent jobs (no document text is stored) and clearing history + translation memory.
import { call } from "../api.js";
import { show } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast, confirmDialog } from "../ui.js";

export const historyView = {
  async render() {
    const h = await call("history");
    const rows = h.jobs.map((j) => el("tr", {},
      el("td", { class: "muted small", style: "white-space:nowrap" }, `${j.finished_at} UTC`),
      el("td", {}, el("strong", {}, j.file_name)),
      el("td", {}, `${j.source_lang} → ${j.target_lang}`),
      el("td", { class: "muted small" }, j.model),
      el("td", {}, `${j.translated}/${j.segments}`),
      el("td", {}, j.warnings ? el("span", { class: "chip warn" }, `${j.warnings}`) : el("span", { class: "chip ok" }, "0")),
      el("td", { class: "muted" }, `${Math.round(j.seconds)} s`)));
    const clear = btn("Clear history…", { kind: "danger", icon: "trash", onclick: async () => {
      const ok = await confirmDialog("Clear history?",
        "This deletes the job list and all stored translations (translation memory) on this PC. Your glossaries are kept. This cannot be undone.",
        "Clear", true);
      if (!ok) return;
      const r = await call("clear_history");
      toast(`Deleted ${r.jobs} job records and ${r.memory} stored translations`);
      show("history");
    } });
    return el("section", { class: "view wide" },
      el("div", {}, el("h1", {}, "History"),
        el("p", { class: "sub" }, "Recent translations on this PC. Only file names and counts are kept here — never document text.")),
      el("div", { class: "card card-row" }, icon("info"),
        el("div", { style: "flex:1" }, el("strong", {}, `${h.memory} stored translation${h.memory === 1 ? "" : "s"}`),
          el("div", { class: "muted small" }, "The translation memory reuses earlier work. It contains document text and is stored only in your user folder: ", h.data_dir)),
        clear),
      el("div", { class: "table-wrap" }, el("table", { class: "table" },
        el("thead", {}, el("tr", {}, ["When", "File", "Languages", "Model", "Paragraphs", "Warnings", "Time"].map((t) => el("th", {}, t)))),
        el("tbody", {}, rows.length ? rows : el("tr", {}, el("td", { colspan: 7, class: "empty" }, "No translations yet."))))));
  },
};
