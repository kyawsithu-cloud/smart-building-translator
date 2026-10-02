// Glossary: search, add/edit/delete, do-not-translate, priority, context; import/export CSV.
import { call } from "../api.js";
import { state, show } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast, dialog, confirmDialog } from "../ui.js";

let current = null;
let search = "";

export const glossaryView = {
  async render() {
    const names = state.info.glossaries;
    current = current && names.includes(current) ? current : state.info.settings.glossary || names[0];
    const terms = await call("glossary_terms", current, search);
    const picker = el("select", { onchange: (e) => { current = e.target.value; show("glossary"); } },
      names.map((n) => el("option", { value: n, selected: n === current }, n)));
    const box = el("input", { type: "search", placeholder: "Search terms…", value: search });
    let debounce;
    box.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => { search = box.value; show("glossary"); }, 300); });
    const drafts = terms.filter((t) => t.draft).length;
    const rows = terms.map((t) => el("tr", {},
      el("td", {}, el("strong", {}, t.source_term)),
      el("td", {}, t.do_not_translate ? el("span", { class: "muted" }, "(kept as-is)") : t.target_term),
      el("td", { class: "muted small" }, `${t.source_lang} → ${t.target_lang}`),
      el("td", {}, el("div", { class: "chips" },
        t.do_not_translate ? el("span", { class: "chip accent" }, "do not translate") : null,
        t.priority !== "normal" ? el("span", { class: "chip" }, `${t.priority} priority`) : null,
        t.context ? el("span", { class: "chip", title: "Used only on slides/pages mentioning these words" }, `context: ${t.context}`) : null,
        t.draft ? el("span", { class: "chip warn", title: t.notes }, "draft — please check") : null,
        t.category ? el("span", { class: "chip" }, t.category) : null)),
      el("td", { style: "white-space:nowrap" },
        btn("", { kind: "icon", icon: "edit", title: "Edit", onclick: () => editTerm(t) }),
        btn("", { kind: "icon", icon: "trash", title: "Delete", onclick: () => deleteTerm(t) }))));
    return el("section", { class: "view wide" },
      el("div", {}, el("h1", {}, "Glossary"),
        el("p", { class: "sub" }, "Approved translations are always used. Mark product, protocol and company names “do not translate”.")),
      el("div", { class: "toolbar" },
        el("label", { class: "field", style: "flex-direction:row;align-items:center" }, "Glossary", picker), box,
        el("span", { style: "flex:1" }),
        btn("Import CSV", { icon: "import", onclick: importCsv }),
        btn("Export CSV", { icon: "export", onclick: exportCsv }),
        btn("Add term", { kind: "primary", icon: "plus", onclick: () => editTerm(null) })),
      drafts ? el("div", { class: "note warn" }, icon("alert"), `${drafts} entr${drafts === 1 ? "y is" : "ies are"} marked draft — check that the translation is what your organisation uses.`) : null,
      state.result && state.result.doc_terms ? el("div", { class: "note" }, icon("book"),
        el("div", { style: "flex:1" }, "The last translation produced a term sheet of recurring terms. Correct it in Excel first, then import it."),
        btn("Open term sheet", { onclick: () => call("open_result", "terms") }),
        btn("Import it", { onclick: importLastTerms })) : null,
      el("div", { class: "table-wrap" }, el("table", { class: "table" },
        el("thead", {}, el("tr", {}, ["Source term", "Translation", "Languages", "Rules", ""].map((h) => el("th", {}, h)))),
        el("tbody", {}, rows.length ? rows : el("tr", {}, el("td", { colspan: 5, class: "empty" }, search ? "No matching terms." : "No terms yet."))))),
      el("div", { class: "muted small" }, `${terms.length} term${terms.length === 1 ? "" : "s"}`));
  },
};

async function editTerm(t) {
  const langs = state.info.languages;
  const f = (name, value, attrs = {}) => { const i = el("input", { type: "text", value: value || "", ...attrs }); i.name = name; return i; };
  const langSel = (name, value) => { const s = el("select", {}, langs.map((l) => el("option", { value: l.code, selected: l.code === value }, l.name))); s.name = name; return s; };
  const src = f("source_term", t && t.source_term), tgt = f("target_term", t && t.target_term);
  const sl = langSel("source_lang", t ? t.source_lang : "en"), tl = langSel("target_lang", t ? t.target_lang : "ja");
  const dnt = el("input", { type: "checkbox", checked: t ? t.do_not_translate : false });
  const prio = el("select", {}, ["low", "normal", "high"].map((p) => el("option", { value: p, selected: (t ? t.priority : "normal") === p }, p)));
  const ctx = f("context", t && t.context, { placeholder: "e.g. screen, display" });
  const cat = f("category", t && t.category), notes = f("notes", t && t.notes);
  const toggle = () => { tgt.disabled = dnt.checked; };
  dnt.addEventListener("change", toggle); toggle();
  const body = el("div", { class: "form-grid" },
    el("label", { class: "field" }, "Source term", src), el("label", { class: "field" }, "Translation", tgt),
    el("label", { class: "field" }, "Source language", sl), el("label", { class: "field" }, "Target language", tl),
    el("label", { class: "switch full" }, dnt, el("div", {}, el("div", { class: "t" }, "Do not translate"),
      el("div", { class: "d" }, "Keep exactly as written in every language (product names, protocols, acronyms)."))),
    el("label", { class: "field" }, "Priority", prio),
    el("label", { class: "field" }, "Only when these words are on the slide/page", ctx),
    el("label", { class: "field" }, "Category", cat), el("label", { class: "field" }, "Notes", notes));
  const ok = await dialog({ title: t ? "Edit term" : "Add term", body, wide: true,
    buttons: [{ label: "Cancel", value: false }, { label: "Save", value: true, kind: "primary" }] });
  if (!ok) return;
  try {
    await call("glossary_save", current, { id: t && t.id, source_term: src.value, target_term: dnt.checked ? src.value : tgt.value,
      source_lang: sl.value, target_lang: tl.value, do_not_translate: dnt.checked, priority: prio.value,
      context: ctx.value, category: cat.value, notes: t && t.draft && notes.value === t.notes ? notes.value.replace(/DRAFT\s*[—-]?\s*/i, "").trim() : notes.value });
    toast("Saved");
    show("glossary");
  } catch (e) { toast(e.message, "err"); }
}

async function deleteTerm(t) {
  if (!(await confirmDialog("Delete term?", `“${t.source_term}” will be removed from the glossary.`, "Delete", true))) return;
  await call("glossary_delete", t.id);
  show("glossary");
}

async function importCsv() {
  try {
    const n = await call("glossary_import", current);
    if (n) { toast(`Imported ${n} terms`); show("glossary"); }
  } catch (e) { toast(e.message, "err"); }
}

async function importLastTerms() {
  if (!(await confirmDialog("Import the term sheet?", "Only import after checking the translations in the term sheet (rows marked UNRESOLVED need a decision). Existing entries with the same term are updated.", "Import"))) return;
  try { toast(`Imported ${await call("glossary_import_terms_of_last_job", current)} terms`); show("glossary"); }
  catch (e) { toast(e.message, "err"); }
}

async function exportCsv() {
  try {
    const path = await call("glossary_export", current);
    if (path) toast(`Exported to ${path}`);
  } catch (e) { toast(e.message, "err"); }
}
