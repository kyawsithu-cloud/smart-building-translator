// Quality-check results: the four-row summary (result screens) and the document checks panel (Review).
import { icon } from "./icons.js";
import { el, btn } from "./ui.js";

export const CATEGORY_ORDER = ["terminology", "completeness", "identifiers", "layout"];
export const OTHER = "(other wording)";
// Findings about the document as a whole (shown in the panel); the rest are shown on their paragraph's row.
const DOC_LEVEL = new Set(["term_variants", "same_source_differs", "glossary_term", "picture_text", "not_translatable",
  "substitute_font", "font_not_installed", "missing_glyphs", "formatting_simplified"]);

export const sevKind = (s) => (s === "error" ? "err" : s === "warning" ? "warn" : "info");

export function hasProblems(q) {
  return CATEGORY_ORDER.some((k) => q.summary[k].errors || q.summary[k].warnings);
}

function statusText(s) {
  const parts = [];
  if (s.errors) parts.push(`${s.errors} error${s.errors === 1 ? "" : "s"}`);
  if (s.warnings) parts.push(`${s.warnings} to check`);
  return parts.join(", ") || "OK";
}

export function qualitySummary(q, onOpen) {
  return el("div", { class: "qc-summary" }, CATEGORY_ORDER.map((key) => {
    const s = q.summary[key];
    const mine = q.findings.filter((f) => f.category === key && f.severity !== "info");
    const kind = s.errors ? "err" : s.warnings ? "warn" : "ok";
    return el("button", { type: "button", class: `qc-row ${kind}`, disabled: !mine.length, onclick: () => onOpen(key),
                          title: mine.length ? "Show in Review" : null },
      el("span", { class: `qc-dot ${kind}` }, icon(kind === "ok" ? "check" : "alert")),
      el("span", { class: "qc-label" }, s.label),
      el("span", { class: "qc-first" }, [...new Set(mine.map((f) => f.text))].slice(0, 2).join(" · ")),
      el("span", { class: `qc-status ${kind}` }, statusText(s)));
  }));
}

function where(pages, unit) {
  if (!pages.length) return "";
  const shown = pages.slice(0, 8).join(", ") + (pages.length > 8 ? "…" : "");
  return `${unit}${pages.length === 1 ? "" : "s"} ${shown}`;
}

export function findingsPanel(findings, { unit, readOnly, onShow, onApply }) {
  const doc = findings.filter((f) => DOC_LEVEL.has(f.code));
  if (!doc.length) return null;
  const item = (f) => {
    const variants = f.variants && f.variants.length > 1 ? el("div", { class: "chips" }, f.variants.map((v) => {
      const majority = f.majority ? v.text === f.majority : false;
      return el("span", { class: `chip ${majority ? "ok" : ""}`, title: `${v.count} paragraph(s)` },
        `${v.text} × ${v.count}`,
        !readOnly && v.text !== OTHER ? el("button", { type: "button", class: "chip-action",
          title: "Use this wording in all of these paragraphs", onclick: () => onApply(f, v.text) }, "use everywhere") : null);
    })) : null;
    return el("div", { class: "qc-item" },
      el("span", { class: `qc-dot ${sevKind(f.severity)}` }, icon(f.severity === "info" ? "info" : "alert")),
      el("div", { class: "qc-body" },
        el("div", {}, f.text),
        el("div", { class: "muted small" }, [f.category_label, where(f.pages, unit)].filter(Boolean).join(" · ")),
        variants),
      f.segments.length ? btn("Show", { onclick: () => onShow(f) }) : null);
  };
  const shown = doc.slice(0, 6), rest = doc.slice(6);
  return el("div", { class: "card qc-panel" },
    el("div", { class: "card-row" }, el("h2", { style: "margin:0;flex:1" }, "Document checks"),
      el("span", { class: "muted small" }, "Consistency across the whole document")),
    shown.map(item),
    rest.length ? el("details", {}, el("summary", {}, `${rest.length} more`), rest.map(item)) : null);
}
