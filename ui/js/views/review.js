// Review: original and translation side by side; edit translations, then rebuild the document.
import { call } from "../api.js";
import { state, show, setReviewBadge } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast, richText } from "../ui.js";

let filter = "all";
let query = "";

export const reviewView = {
  async render() {
    const items = await call("review_items");
    const root = el("section", { class: "view wide" },
      el("div", {}, el("h1", {}, "Review"),
        el("p", { class: "sub" }, "Check the translation next to the original. Click a translation to correct it; your corrections are remembered for next time.")));
    if (!items.length) {
      root.append(el("div", { class: "card empty" }, icon("review", "i big-icon"),
        el("p", {}, "Translate a document first — it will appear here for review."),
        btn("Go to Translate", { kind: "primary", onclick: () => show("translate") })));
      return root;
    }
    const counts = { all: items.length, flagged: items.filter((i) => i.flagged).length,
                     edited: items.filter((i) => i.status === "edited").length };
    const rebuild = btn("Save & rebuild document", { kind: "primary", icon: "refresh", disabled: !state.reviewDirty,
      onclick: async () => {
        rebuild.disabled = true;
        try {
          state.result = await call("rebuild");
          state.reviewDirty = false;
          setReviewBadge(state.result.flagged);
          toast(`Saved: ${state.result.output_name}`);
          show("review");
        } catch (e) { toast(e.message, "err"); rebuild.disabled = false; }
      } });
    const seg = el("div", { class: "seg" }, [["all", "All"], ["flagged", "Needs a look"], ["edited", "Edited"]].map(([k, l]) =>
      el("button", { type: "button", class: filter === k ? "on" : "", onclick: () => { filter = k; show("review"); } }, `${l} (${counts[k]})`)));
    const search = el("input", { type: "search", placeholder: "Search text…", value: query });
    const body = el("tbody");
    const paint = () => {
      const q = query.toLowerCase();
      const rows = items.filter((i) => (filter === "all" || (filter === "flagged" ? i.flagged : i.status === "edited"))
        && (!q || i.source.toLowerCase().includes(q) || i.translation.toLowerCase().includes(q)));
      body.replaceChildren(...(rows.length ? rows.map(row) : [el("tr", {}, el("td", { colspan: 4, class: "empty" }, "Nothing to show."))]));
    };
    search.addEventListener("input", () => { query = search.value; paint(); });
    paint();
    root.append(...[
      el("div", { class: "toolbar" }, seg, search, el("span", { class: "spacer", style: "flex:1" }),
        state.result ? btn("Open file", { icon: "open", onclick: () => call("open_result", "file") }) : null, rebuild),
      state.reviewDirty ? el("div", { class: "note" }, icon("info"), "You have corrections that are not in the document yet — click “Save & rebuild document”.") : null,
      el("div", { class: "table-wrap" },
        el("table", { class: "table" },
          el("thead", {}, el("tr", {}, el("th", { style: "width:70px" }, "Where"), el("th", {}, "Original"), el("th", {}, "Translation"), el("th", { style: "width:200px" }, "Checks"))),
          body))].filter(Boolean));
    return root;

    function row(it) {
      const tgt = el("td", { class: "tgt", title: "Click to edit" }, richText(it.translation));
      const tr = el("tr", { class: `rv-row ${it.flagged ? "flagged" : ""} ${it.status === "edited" ? "edited" : ""}` },
        el("td", {}, el("div", {}, `${it.page}`), el("div", { class: "meta" }, it.kind.replace("_", " "))),
        el("td", { class: "src" }, richText(it.source)),
        tgt,
        el("td", {}, el("div", { class: "chips" },
          it.status === "edited" ? el("span", { class: "chip accent" }, "edited by you") : null,
          it.ocr ? el("span", { class: "chip", title: "Read from a scanned page" }, "OCR") : null,
          it.problem_text.map((p) => el("span", { class: "chip warn" }, p)),
          !it.flagged && it.status !== "edited" && it.status !== "kept" ? el("span", { class: "chip ok" }, "ok") : null,
          it.status === "kept" ? el("span", { class: "chip" }, "unchanged") : null)));
      tgt.addEventListener("click", () => edit(it, tgt), { once: true });
      return tr;
    }

    function edit(it, cell) {
      const area = el("textarea", { rows: Math.max(2, Math.ceil(it.translation.length / 60)) });
      area.value = it.translation;
      const hint = el("div", { class: "meta" }, it.has_tags ? "Keep the markers [1]…[/1] around the words that are bold/coloured in the original." : "Ctrl+Enter to save, Esc to cancel.");
      const save = async () => {
        try {
          const res = await call("save_edit", it.id, area.value);
          it.translation = res.translation; it.status = "edited"; it.flagged = false; it.problem_text = [];
          state.reviewDirty = true;
          if (res.warnings.length) toast(`Saved with notes: ${res.warnings.join(" ")}`);
          show("review");
        } catch (e) { toast(e.message, "err"); }
      };
      const cancel = () => show("review");
      area.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); save(); }
        if (e.key === "Escape") cancel();
      });
      cell.replaceChildren(area, hint, el("div", { class: "actions", style: "margin-top:6px" },
        btn("Save", { kind: "primary", icon: "check", onclick: save }), btn("Cancel", { onclick: cancel })));
      area.focus();
    }
  },
};
