// Models & hardware: detected hardware, recommendation (measured speeds only), install/delete components.
import { call } from "../api.js";
import { show, state } from "../app.js";
import { icon } from "../icons.js";
import { el, btn, toast, dialog, confirmDialog } from "../ui.js";

let timer = null;

export const modelsView = {
  async render() {
    const sys = await call("system");
    const hw = sys.hardware, rec = sys.recommendation;
    const gpu = hw.gpus[0];
    const tile = (label, value, detail) => el("div", { class: "tile" }, el("div", { class: "l" }, label),
      el("div", { style: "font-weight:600;margin-top:2px" }, value), detail ? el("div", { class: "muted small" }, detail) : null);
    const root = el("section", { class: "view" },
      el("div", {}, el("h1", {}, "Models & hardware"),
        el("p", { class: "sub" }, "Everything runs on this computer. Downloads happen only when you click Download.")),
      el("div", { class: "grid-4" },
        tile("Processor", hw.cpu, `${hw.cores} threads`), tile("Memory", `${hw.ram_gib} GB RAM`),
        tile("Graphics", gpu ? gpu.name : "No NVIDIA GPU", gpu ? `${(gpu.vram_total_mib / 1024).toFixed(1)} GB VRAM · ${(gpu.vram_free_mib / 1024).toFixed(1)} GB free` : "CPU will be used"),
        tile("System", hw.os.split(" (")[0])),
      el("div", { class: "card" }, el("h2", {}, `Recommended: ${rec.model} on ${rec.placement}`),
        el("p", { class: "muted", style: "margin:0" }, rec.expectation),
        rec.notes.map((n) => el("div", { class: "note warn", style: "margin-top:10px" }, icon("alert"), n))),
      folderCard(sys.runtime),
      el("div", { class: "card" }, el("h2", {}, "Components"),
        el("table", { class: "table" }, el("tbody", {}, sys.items.map((it) => row(it, sys.download))))));
    clearInterval(timer);
    if (sys.download.status === "running") timer = setInterval(async () => {
      const d = await call("download_status");
      if (d.status !== "running") {
        clearInterval(timer); timer = null;
        toast(d.status === "done" ? "Installed and verified" : d.message, d.status === "done" ? "" : "err");
        await refreshInfo();
      }
      show("models");
    }, 1000);
    return root;
  },
  leave() { clearInterval(timer); timer = null; },
};

// Where the engine and models are kept: e.g. a folder copied from another PC (no new download) or a larger drive.
function folderCard(rt) {
  const change = async (method) => {
    try { await call(method); await refreshInfo(); show("models"); } catch (e) { toast(e.message, "err"); }
  };
  return el("div", { class: "card" },
    el("div", { class: "card-row" },
      el("div", { style: "flex:1;min-width:0" }, el("h2", { style: "margin:0 0 4px" }, "Models folder"),
        el("div", { class: "path" }, rt.path),
        el("div", { class: "muted small", style: "margin-top:4px" },
          `${rt.free_gb != null ? `${rt.free_gb} GB free on this drive. ` : ""}Already have the models (e.g. copied from another PC)? Choose that folder instead of downloading again.`)),
      btn("Change…", { icon: "folder", onclick: () => change("choose_runtime_dir") }),
      rt.custom ? btn("Use default", { onclick: () => change("reset_runtime_dir") }) : null));
}

async function refreshInfo() {
  try { state.info = await call("app_info"); } catch { /* keep the old state */ }
}

function row(it, dl) {
  const running = dl.status === "running" && dl.item === it.id;
  const status = it.installed ? el("span", { class: "chip ok" }, icon("check"), "installed")
    : running ? el("span", { class: "chip accent" }, `downloading ${dl.percent}%`) : el("span", { class: "chip" }, "not installed");
  const actions = [];
  if (!it.installed && !running) actions.push(btn("Download", { icon: "download", disabled: dl.status === "running", onclick: () => download(it) }));
  if (it.installed && it.deletable) actions.push(btn("", { kind: "icon", icon: "trash", title: "Delete", onclick: () => remove(it) }));
  return el("tr", {},
    el("td", {}, el("strong", {}, it.label), el("div", { class: "muted small" }, it.purpose),
      it.languages.length ? el("div", { class: "meta" }, `Languages: ${it.languages.join(", ")}`) : null,
      running ? el("div", { class: "bar", style: "margin-top:8px" }, el("div", { style: `width:${dl.percent}%` })) : null),
    el("td", { class: "muted small", style: "white-space:nowrap" }, it.size, el("br"), it.licence),
    el("td", {}, status),
    el("td", { style: "text-align:right;white-space:nowrap" }, actions));
}

async function download(it) {
  const ok = await dialog({ title: `Download ${it.label}?`, buttons: [{ label: "Cancel", value: false }, { label: "Download", value: true, kind: "primary" }],
    body: el("div", { style: "display:flex;flex-direction:column;gap:8px" },
      el("div", {}, el("strong", {}, "Size: "), it.size), el("div", {}, el("strong", {}, "Source: "), it.source),
      el("div", {}, el("strong", {}, "Licence: "), it.licence),
      el("div", { class: "note" }, icon("shield"), "The file is checked against its published SHA-256 fingerprint and deleted if it does not match. Program files are scanned by Windows Defender. This download is the only time the app uses the internet, and no document data is involved.")) });
  if (!ok) return;
  try { await call("download", it.id); show("models"); } catch (e) { toast(e.message, "err"); }
}

async function remove(it) {
  if (!(await confirmDialog(`Delete ${it.label}?`, `This frees ${it.size}. You can download it again later.`, "Delete", true))) return;
  try { await call("delete_model", it.id); toast("Deleted"); show("models"); } catch (e) { toast(e.message, "err"); }
}
