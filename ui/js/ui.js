// DOM helpers, toasts and dialogs. All text is inserted as text (never as HTML) unless built here.
import { icon } from "./icons.js";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(node.dataset, v);
    else if (v === true) node.setAttribute(k, "");
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function btn(label, opts = {}) {
  const b = el("button", { class: `btn ${opts.kind || ""}`.trim(), type: "button", title: opts.title,
                           disabled: opts.disabled, onclick: opts.onclick });
  if (opts.icon) b.append(icon(opts.icon));
  if (label) b.append(label);
  return b;
}

export function toast(message, kind = "") {
  const t = el("div", { class: `toast ${kind}` }, message);
  document.getElementById("toasts").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
}

// Modal dialog. Returns a promise resolving to the clicked button's value (or null when dismissed).
export function dialog({ title, body, buttons = [{ label: "OK", value: true, kind: "primary" }], wide = false }) {
  const backdrop = document.getElementById("modal");
  return new Promise((resolve) => {
    const close = (value) => { backdrop.classList.add("hidden"); backdrop.replaceChildren(); resolve(value); };
    const box = el("div", { class: "modal", role: "dialog", "aria-modal": "true", style: wide ? "width:min(760px,100%)" : null },
      el("h2", {}, title),
      body instanceof Node ? body : el("div", { class: "muted" }, body),
      el("div", { class: "actions", style: "justify-content:flex-end" },
        buttons.map((b) => btn(b.label, { kind: b.kind, onclick: () => close(b.value) }))));
    backdrop.replaceChildren(box);
    backdrop.classList.remove("hidden");
    backdrop.onclick = (e) => { if (e.target === backdrop) close(null); };
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { document.removeEventListener("keydown", esc); close(null); }
    });
    const first = box.querySelector("input, select, textarea, .btn.primary");
    if (first) first.focus();
  });
}

export const confirmDialog = (title, body, okLabel = "Continue", danger = false) => dialog({
  title, body, buttons: [{ label: "Cancel", value: false }, { label: okLabel, value: true, kind: danger ? "primary danger" : "primary" }],
});

export function pct(v) { return v == null ? "n/a" : `${Number(v).toFixed(v >= 99.95 ? 0 : 1)}%`; }
export function langName(code, languages) { return (languages.find((l) => l.code === code) || {}).name || code; }

// Formatting markers [1]…[/1] shown as small chips in read-only text.
export function richText(text) {
  const frag = document.createDocumentFragment();
  for (const part of String(text).split(/(\[\/?\d+\])/)) {
    if (/^\[\/?\d+\]$/.test(part)) frag.append(el("span", { class: "tag", title: "Formatting marker" }, part));
    else if (part) frag.append(part);
  }
  return frag;
}
