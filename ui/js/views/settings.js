// Settings: only the few choices that matter. Saved to the user's settings file on this PC.
import { call } from "../api.js";
import { state, applyTheme } from "../app.js";
import { icon } from "../icons.js";
import { el, toast } from "../ui.js";

export const settingsView = {
  async render() {
    const s = await call("get_settings");
    const save = async (changes) => {
      try {
        const saved = await call("save_settings", changes);
        state.info.settings = saved;
        if ("theme" in changes) applyTheme(saved.theme);
        toast("Saved");
      } catch (e) { toast(e.message, "err"); }
    };
    const theme = el("div", { class: "seg" }, [["system", "System"], ["light", "Light"], ["dark", "Dark"]].map(([k, l]) =>
      el("button", { type: "button", class: s.theme === k ? "on" : "", onclick: (e) => {
        theme.querySelectorAll("button").forEach((b) => b.classList.remove("on")); e.currentTarget.classList.add("on"); save({ theme: k }); } }, l)));
    const toggle = (title, desc, checked, onchange) => {
      const input = el("input", { type: "checkbox", checked });
      input.addEventListener("change", () => onchange(input.checked));
      return el("label", { class: "switch" }, input, el("div", {}, el("div", { class: "t" }, title), el("div", { class: "d" }, desc)));
    };
    const target = el("select", { onchange: (e) => save({ target_lang: e.target.value }) },
      el("option", { value: "", selected: !s.target_lang }, "Automatic — English ↔ Japanese, other languages → English"),
      state.info.languages.map((l) => el("option", { value: l.code, selected: s.target_lang === l.code }, l.name)));
    return el("section", { class: "view" },
      el("div", {}, el("h1", {}, "Settings")),
      el("div", { class: "card" }, el("h2", {}, "Appearance"), theme),
      el("div", { class: "card" }, el("h2", {}, "Usually translate into"),
        el("label", { class: "field", style: "max-width:520px" }, target),
        el("p", { class: "muted small", style: "margin:8px 0 0" }, "Preselected for every document; you can still choose another language before translating.")),
      el("div", { class: "card", style: "display:flex;flex-direction:column;gap:16px" }, el("h2", { style: "margin:0" }, "Translation"),
        toggle("Keep recurring terms consistent", "Terms that appear several times are translated the same way throughout the document.",
          s.doc_terms !== "off", (v) => save({ doc_terms: v ? "vote" : "off" })),
        toggle("Re-check flagged paragraphs with a second model", "Uses Qwen3 for paragraphs that still have problems after retries (slower; needs the Qwen3 model).",
          s.repair_model === "qwen3-8b", (v) => save({ repair_model: v ? "qwen3-8b" : "" })),
        toggle("Use the graphics card (GPU)", "Turn off if a game or other program needs the GPU; translation then runs on the processor (much slower).",
          s.gpu !== "cpu", (v) => save({ gpu: v ? "auto" : "cpu" }))),
      el("div", { class: "card", style: "display:flex;flex-direction:column;gap:16px" }, el("h2", { style: "margin:0" }, "Privacy"),
        toggle("Translation memory", "Remember translations on this PC to reuse them later. Contains document text; clear it under History.",
          s.use_memory, (v) => save({ use_memory: v })),
        el("div", { class: "note ok" }, icon("shield"),
          el("div", {}, el("strong", {}, "Offline mode. "), "Documents are translated on this computer only. The app blocks all internet connections while it runs; the only exception is a model download that you start yourself under Models.")),
        el("div", { class: "muted small" }, "Your data folder: ", el("span", { class: "path" }, state.info.data_dir))));
  },
};
