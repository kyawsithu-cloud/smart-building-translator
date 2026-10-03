// Review: original and translation side by side with the quality checks; edit translations, then rebuild.
// For a checked translation (made elsewhere) the view is read-only.
import { call } from "../api.js";
import { state, show, setReviewBadge } from "../app.js";
import { icon } from "../icons.js";
import { CATEGORY_ORDER, findingsPanel, sevKind } from "../quality.js";
import { el, btn, toast, richText } from "../ui.js";

let filter = "all";
let category = "";
let focus = null;          // {ids: Set, text} — paragraphs of one finding
let query = "";
let compare = false;       // side-by-side page pictures
let comparePage = 1;

export const reviewView = {
  async render() {
    const [items, findings] = await Promise.all([call("review_items"), call("review_findings")]);
    const readOnly = !!(state.result && state.result.kind === "check");
    if (state.reviewCategory) { category = state.reviewCategory; filter = "all"; focus = null; state.reviewCategory = null; }
    const root = el("section", { class: "view wide" },
      el("div", {}, el("h1", {}, "Review"),
        el("p", { class: "sub" }, readOnly
          ? "Findings for the translation you checked, next to the original."
          : "Check the translation next to the original. Click a translation to correct it; your corrections are remembered for next time.")));
    if (!items.length) {
      root.append(el("div", { class: "card empty" }, icon("review", "i big-icon"),
        el("p", {}, "Translate or check a document first — it will appear here for review."),
        btn("Go to Translate", { kind: "primary", onclick: () => show("translate") })));
      return root;
    }
    const unit = state.result && /\.pdf$/i.test(state.result.input || "") ? "page" : "slide";
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
    const tabs = [["all", "All"], ["flagged", "Needs a look"], ...(readOnly ? [] : [["edited", "Edited"]])];
    const seg = el("div", { class: "seg" }, tabs.map(([k, l]) =>
      el("button", { type: "button", class: filter === k ? "on" : "", onclick: () => { filter = k; focus = null; show("review"); } }, `${l} (${counts[k]})`)));
    const labels = Object.fromEntries(findings.map((f) => [f.category, f.category_label]));
    const pick = el("select", { title: "Show one kind of check", onchange: (e) => { category = e.target.value; focus = null; show("review"); } },
      el("option", { value: "" }, "All checks"),
      CATEGORY_ORDER.map((k) => el("option", { value: k, selected: category === k },
        `${labels[k] || k[0].toUpperCase() + k.slice(1)} (${items.filter((i) => i.categories.includes(k)).length})`)));
    const search = el("input", { type: "search", placeholder: "Search text…", value: query });
    const body = el("tbody");
    const paint = () => {
      const q = query.toLowerCase();
      const rows = items.filter((i) =>
        (focus ? focus.ids.has(i.id) : (filter === "all" || (filter === "flagged" ? i.flagged : i.status === "edited"))
          && (!category || i.categories.includes(category)))
        && (!q || i.source.toLowerCase().includes(q) || i.translation.toLowerCase().includes(q)));
      body.replaceChildren(...(rows.length ? rows.map(row) : [el("tr", {}, el("td", { colspan: 4, class: "empty" }, "Nothing to show."))]));
    };
    search.addEventListener("input", () => { query = search.value; paint(); });
    paint();

    const onShow = (f) => {
      focus = { ids: new Set(f.segments), text: f.text };
      if (f.pages.length) comparePage = f.pages[0];
      show("review");
    };
    const onApply = async (f, text) => {
      try {
        const n = await call("apply_variant", f.index, text);
        state.reviewDirty = state.reviewDirty || n > 0;
        toast(n ? `Changed ${n} paragraph${n === 1 ? "" : "s"}. Click “Save & rebuild document” to write them.` : "Nothing to change.");
        show("review");
      } catch (e) { toast(e.message, "err"); }
    };
    root.append(...[
      readOnly ? el("div", { class: "note" }, icon("info"), "Checking a translation made elsewhere: the file is not changed here. Correct it in the original tool, or export the findings.") : null,
      findingsPanel(findings, { unit, readOnly, onShow, onApply }),
      el("div", { class: "toolbar" }, seg, pick, search, el("span", { class: "spacer", style: "flex:1" }),
        btn(compare ? "Hide pages" : "Compare pages", { icon: "compare", title: "Original and translated pages side by side",
          onclick: () => { compare = !compare; show("review"); } }),
        btn("Export checks", { icon: "download", title: "Save the findings with the text concerned (CSV)", onclick: async () => {
          try { const p = await call("export_checks"); if (p) toast(`Saved: ${p}`); } catch (e) { toast(e.message, "err"); } } }),
        state.result ? btn("Open file", { icon: "open", onclick: () => call("open_result", "file") }) : null,
        readOnly ? null : rebuild),
      focus ? el("div", { class: "note" }, icon("filter"), el("div", { style: "flex:1" }, `Showing the paragraphs for: ${focus.text}`),
        btn("Show all", { onclick: () => { focus = null; show("review"); } })) : null,
      compare ? comparePanel(unit, items) : null,
      state.reviewDirty && !readOnly ? el("div", { class: "note" }, icon("info"), "You have corrections that are not in the document yet — click “Save & rebuild document”.") : null,
      el("div", { class: "table-wrap" },
        el("table", { class: "table" },
          el("thead", {}, el("tr", {}, el("th", { style: "width:70px" }, "Where"), el("th", {}, "Original"), el("th", {}, "Translation"), el("th", { style: "width:240px" }, "Checks"))),
          body))].filter(Boolean));
    return root;

    function row(it) {
      const tgt = el("td", { class: "tgt", title: readOnly ? null : "Click to edit" }, richText(it.translation));
      const tr = el("tr", { class: `rv-row ${it.flagged ? "flagged" : ""} ${it.status === "edited" ? "edited" : ""}` },
        el("td", { class: "where", title: `Show ${unit} ${it.page} side by side`,
                   onclick: () => { comparePage = it.page; compare = true; show("review"); } },
          el("div", {}, `${it.page}`), el("div", { class: "meta" }, it.kind.replace("_", " "))),
        el("td", { class: "src" }, richText(it.source)),
        tgt,
        el("td", {}, el("div", { class: "chips" },
          it.status === "edited" ? el("span", { class: "chip accent" }, "edited by you") : null,
          it.ocr ? el("span", { class: "chip", title: "Read from a scanned page" }, "OCR") : null,
          it.checks.map((c) => el("span", { class: `chip ${sevKind(c.severity) === "info" ? "" : sevKind(c.severity)}` }, c.text)),
          !it.flagged && it.status !== "edited" && it.status !== "kept" && !it.checks.length ? el("span", { class: "chip ok" }, "ok") : null,
          it.status === "kept" ? el("span", { class: "chip" }, "unchanged") : null)));
      if (!readOnly) tgt.addEventListener("click", () => edit(it, tgt), { once: true });
      return tr;
    }

    function edit(it, cell) {
      const area = el("textarea", { rows: Math.max(2, Math.ceil(it.translation.length / 60)) });
      area.value = it.translation;
      const hint = el("div", { class: "meta" }, it.has_tags ? "Keep the markers [1]…[/1] around the words that are bold/coloured in the original." : "Ctrl+Enter to save, Esc to cancel.");
      const save = async () => {
        try {
          const res = await call("save_edit", it.id, area.value);
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

// Original and translated page side by side; paragraphs with findings are outlined on both.
function comparePanel(unit, items) {
  const body = el("div", { class: "pg-body muted" }, "Preparing the pictures…");
  const label = el("span", { class: "pg-label" });
  const go = (n) => { comparePage = n; load(); };
  const prev = btn("", { icon: "chevron-left", title: `Previous ${unit}`, onclick: () => go(comparePage - 1) });
  const next = btn("", { icon: "chevron-right", title: `Next ${unit}`, onclick: () => go(comparePage + 1) });
  const panel = el("div", { class: "card compare" },
    el("div", { class: "card-row" }, el("h2", { style: "margin:0;flex:1" }, "Compare pages"), prev, label, next),
    body);
  async function load() {
    body.replaceChildren(el("div", { class: "muted" }, "Preparing the pictures…"));
    try {
      const v = await call("page_view", comparePage);
      comparePage = v.page;
      label.textContent = `${v.unit[0].toUpperCase() + v.unit.slice(1)} ${v.page} of ${v.pages}`;
      prev.disabled = v.page <= 1; next.disabled = v.page >= v.pages;
      if (!v.available) { body.replaceChildren(el("div", { class: "note" }, icon("info"), v.reason)); return; }
      const flagged = items.filter((i) => i.page === v.page && i.flagged).length;
      const figure = (title, src) => el("figure", {}, el("figcaption", {}, title),
        el("div", { class: "pg" }, el("img", { src, alt: title }),
          v.boxes.map((b) => el("div", { class: `pg-box ${sevKind(b.severity)}`, title: b.text,
            style: `left:${b.x * 100}%;top:${b.y * 100}%;width:${b.w * 100}%;height:${b.h * 100}%` }))));
      body.replaceChildren(el("div", { class: "pg-pair" }, figure("Original", v.original), figure("Translation", v.translated)),
        el("div", { class: "muted small" }, flagged ? `Outlined: ${flagged} paragraph(s) with findings on this ${v.unit}. Hover an outline for details.`
          : `No findings on this ${v.unit}.`));
    } catch (e) { body.replaceChildren(el("div", { class: "note err" }, icon("alert"), e.message)); }
  }
  load();
  return panel;
}

