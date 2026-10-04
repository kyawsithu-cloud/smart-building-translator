// Fake API with sample data, for working on the UI in a normal browser (index.html?mock). Not used by the app.
const languages = [["en", "English"], ["ja", "Japanese"], ["zh", "Chinese"], ["ko", "Korean"], ["my", "Burmese"],
  ["th", "Thai"], ["de", "German"], ["fr", "French"], ["es", "Spanish"]].map(([code, name]) => ({ code, name }));
let settings = { use_memory: true, repair_model: "qwen3-8b", gpu: "auto", doc_terms: "vote", glossary: "smart-building", theme: "system" };
let job = { status: "idle" };
let t0 = 0;
let items = [
  { id: "s1/2/p0", page: 1, kind: "title", status: "translated", checks: [], categories: [], flagged: false, ocr: false, has_tags: false,
    source: "Smart Building Platform Overview", translation: "スマートビルディングプラットフォーム概要" },
  { id: "s2/3/p0", page: 2, kind: "body", status: "translated", checks: [], categories: [], flagged: false, ocr: false, has_tags: true,
    source: "The [1]Building Management System[/1] monitors and controls HVAC equipment.", translation: "[1]ビル管理システム[/1]は、HVAC機器の監視および制御を行います。" },
  { id: "s2/3/p2", page: 2, kind: "body", status: "retried", checks: [{ category: "terminology", code: "glossary_term", severity: "warning", text: "Glossary: “variable air volume” should be “可変風量”" }], categories: ["terminology"], flagged: true, ocr: false, has_tags: false,
    source: "Variable Air Volume (VAV) terminal control", translation: "可変風量（VAV）端子制御" },
  { id: "s5/3/t1.3/p0", page: 5, kind: "table_cell", status: "kept", checks: [], categories: [], flagged: false, ocr: false, has_tags: false,
    source: "47808", translation: "47808" },
  { id: "s8/3/p0", page: 8, kind: "body", status: "translated", checks: [], categories: [], flagged: false, ocr: false, has_tags: false,
    source: "When a chiller alarm occurs, the system automatically notifies the maintenance team by e-mail and creates a work order.",
    translation: "冷凍機の警報が発生すると、システムは自動的にメールで保守チームに通知し、作業指示を作成します。" },
  { id: "s8/4/p0", page: 8, kind: "body", status: "translated", flagged: true, ocr: false, has_tags: false,
    checks: [{ category: "terminology", code: "term_variants", severity: "warning", text: "“building management system” is “ビル管理システム” in most places" }],
    categories: ["terminology"],
    source: "The building management system sends data to the cloud platform via the BACnet/IP gateway (192.168.1.100).",
    translation: "建物管理システムは、BACnet/IPゲートウェイ（192.168.1.10）経由でクラウドプラットフォームにデータを送信します。" },
];
items[5].checks.push({ category: "identifiers", code: "token_changed", severity: "error", text: "Identifier changed: 192.168.1.100 → 192.168.1.10" });
items[5].categories.push("identifiers");
const findings = [
  { index: 0, category: "identifiers", category_label: "Identifiers and numbers", code: "token_changed", severity: "error",
    text: "Identifier changed: 192.168.1.100 → 192.168.1.10", message: "slide 8: identifier changed", segments: ["s8/4/p0"], pages: [8] },
  { index: 1, category: "terminology", category_label: "Terminology consistency", code: "term_variants", severity: "warning",
    text: "“building management system” is “ビル管理システム” in most places", message: "recurring term worded differently in 1 of 6 paragraphs",
    segments: ["s8/4/p0"], pages: [8], term: "building management system", majority: "ビル管理システム",
    variants: [{ text: "ビル管理システム", count: 5 }, { text: "建物管理システム", count: 1 }] },
  { index: 2, category: "terminology", category_label: "Terminology consistency", code: "glossary_term", severity: "warning",
    text: "Glossary: “variable air volume” should be “可変風量”", message: "approved glossary term not used in 1 of 2 paragraph(s)", segments: ["s2/3/p2"], pages: [2] },
  { index: 3, category: "layout", category_label: "Layout and fonts", code: "overflow", severity: "warning",
    text: "Text may not fit its box", message: "slide 6: text likely exceeds its box even at 80% font size", segments: [], pages: [6] },
  { index: 4, category: "completeness", category_label: "Missing or partial translation", code: "picture_text", severity: "warning",
    text: "slide 4: picture contains text (not translated)", message: "slide 4: picture contains text (not translated)", segments: [], pages: [4] },
  { index: 5, category: "layout", category_label: "Layout and fonts", code: "font_reduced", severity: "info",
    text: "Font made smaller to fit", message: "slide 3: font reduced to 90% to fit", segments: [], pages: [3] },
];
const summary = (fs) => Object.fromEntries([["terminology", "Terminology consistency"], ["completeness", "Missing or partial translation"],
  ["identifiers", "Identifiers and numbers"], ["layout", "Layout and fonts"]].map(([k, label]) => [k, { label,
  errors: fs.filter((f) => f.category === k && f.severity === "error").length,
  warnings: fs.filter((f) => f.category === k && f.severity === "warning").length,
  info: fs.filter((f) => f.category === k && f.severity === "info").length }]));
const quality = () => ({ summary: summary(findings), checked: { paragraphs: 63 }, findings });
const glossary = [
  { id: 1, source_term: "Building Management System", target_term: "ビル管理システム", source_lang: "en", target_lang: "ja", category: "Smart Building", notes: "", do_not_translate: false, priority: "high", context: "", draft: false },
  { id: 2, source_term: "chiller", target_term: "冷凍機", source_lang: "en", target_lang: "ja", category: "HVAC", notes: "DRAFT — review. Alt: チラー", do_not_translate: false, priority: "high", context: "", draft: true },
  { id: 3, source_term: "alarm", target_term: "アラーム", source_lang: "en", target_lang: "ja", category: "Monitoring", notes: "UI label", do_not_translate: false, priority: "normal", context: "screen,display", draft: false },
  { id: 4, source_term: "BACnet", target_term: "BACnet", source_lang: "en", target_lang: "ja", category: "Protocol", notes: "", do_not_translate: true, priority: "high", context: "", draft: false },
];
const result = {
  input: "D:\\Work\\Projects\\Building_System_Overview.pptx", output: "D:\\Work\\Projects\\Building_System_Overview_JA.pptx",
  output_name: "Building_System_Overview_JA.pptx", source: "en", target: "ja", segments: 63, translated_pct: 100, seconds: 38.6,
  checks: { identifiers: 100, glossary: 100, formatting: 100 },
  kind: "translation", notices: [], ocr_segments: 0, doc_terms: 3, doc_terms_unresolved: 0, repaired: 1, edited: 0, flagged: 2,
};
const checkResult = { kind: "check", input: "D:\\Work\\Projects\\Spec.pptx", output: "D:\\Work\\Agency\\Spec_JA_agency.pptx",
  output_name: "Spec_JA_agency.pptx", source: "en", target: "ja", segments: 63, matched: 61, seconds: 41.2, term_note: "", notices: [], flagged: 2 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// Setup guide simulation: a "download" or "copy" that finishes after 6 seconds.
const setupInstalled = { engine: false, "hy-mt2-7b": false, "qwen3-8b": false, "ocr-ko": false, "ocr-th": false };
let setupRun = null;
function setupProgress() {
  const idle = { status: "idle", overall: 0, percent: 0, total_mb: 0, finished: [], verified: [], message: "", asset: "", file: "", copied_mb: 0 };
  if (!setupRun) return { download: idle, copy: idle };
  const pct = Math.min(100, Math.round((Date.now() - setupRun.t0) / 60));
  const status = pct >= 100 ? "done" : "running";
  if (status === "done") { setupRun.items.forEach((i) => { setupInstalled[i] = true; }); }
  const busy = { ...idle, status, overall: pct, percent: pct, total_mb: 6428, asset: "hy-mt2-7b", file: "models/HY-MT2-7B-Q6_K.gguf",
                 copied_mb: Math.round(6428 * pct / 100), finished: pct > 15 ? ["llama-cuda", "cudart"] : [], verified: pct > 50 ? ["hy-mt2-7b"] : [],
                 message: status === "done" ? "Installed and verified" : "" };
  const out = setupRun.kind === "copy" ? { download: idle, copy: busy } : { download: busy, copy: idle };
  if (status === "done") setupRun = null;
  return out;
}

export const mockApi = {
  async app_info() {
    return { version: "1.0.0", setup_done: !!settings.setup_done, mode: "offline", languages, glossaries: ["smart-building"], settings, engine_installed: setupInstalled.engine || !location.search.includes("fresh"),
             model_installed: setupInstalled["hy-mt2-7b"] || !location.search.includes("fresh"), data_dir: "C:\\Users\\you\\AppData\\Local\\SmartBuildingTranslator" };
  },
  async choose_file() { return "D:\\Work\\Projects\\Building_System_Overview.pptx"; },
  async inspect_file(path) {
    await sleep(300);
    return { path, name: path.split("\\").pop(), folder: "D:\\Work\\Projects", type: path.endsWith(".pdf") ? "PDF" : "PPTX",
             size_kb: 1280, pages: 9, paragraphs: 63, detected: "en", confidence: 1, target: "ja", notes: [] };
  },
  async start_translation() { job = { status: "running", kind: "translation", stage: "read", stages_done: [], done: 0, total: 63 }; t0 = Date.now(); return {}; },
  async start_check() { job = { status: "running", kind: "check", stage: "read", stages_done: [], done: 0, total: 0 }; t0 = Date.now(); },
  async page_view(page) {
    await sleep(500);
    const svg = (title, bg) => "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(
      `<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'><rect width='1280' height='720' fill='${bg}'/>` +
      `<rect x='80' y='60' width='1120' height='90' fill='#1d3557'/><text x='110' y='120' font-size='44' fill='#fff' font-family='Segoe UI'>${title}</text>` +
      `<rect x='80' y='200' width='520' height='420' fill='#e9eef5'/><rect x='660' y='200' width='540' height='420' fill='#e9eef5'/></svg>`)));
    const p = Math.max(1, Math.min(9, page));
    return { page: p, pages: 9, unit: "slide", available: true, original: svg(`Slide ${p} — original`, "#ffffff"),
             translated: svg(`スライド ${p} — 翻訳`, "#ffffff"),
             boxes: p === 8 ? [{ segment: "s8/4/p0", x: 0.51, y: 0.27, w: 0.43, h: 0.59, severity: "error", text: "Identifier changed: 192.168.1.100 → 192.168.1.10" }] : [] };
  },
  async export_checks() { return "D:\\Work\\Projects\\Building_System_Overview_JA.checks.csv"; },
  async review_findings() { return job.status === "done" || job.status === "idle" ? findings : []; },
  async apply_variant() { items[5].translation = items[5].translation.replace("建物管理システム", "ビル管理システム"); findings.splice(1, 1); findings.forEach((f, i) => { f.index = i; }); return 1; },
  async job_status() {
    if (job.status !== "running") return job;
    const t = (Date.now() - t0) / 1000;
    const plan = job.kind === "check" ? [["read", 0.8], ["load", 2], ["terms", 4], ["check", 5]]
      : [["read", 0.8], ["load", 2], ["terms", 3], ["translate", 8], ["align", 8.8], ["write", 9.6], ["check", 10.2]];
    const idx = plan.findIndex(([, end]) => t < end);
    if (idx === -1) {
      const r = { ...(job.kind === "check" ? checkResult : result), quality: quality() };
      job = { status: "done", stage: "check", stages_done: plan.map(([k]) => k), done: 63, total: 63, elapsed: t, result: r }; return job;
    }
    const stage = plan[idx][0];
    const done = stage === "translate" ? Math.round(63 * (t - 3) / 5) : stage === "align" || stage === "write" ? 63 : 0;
    return { status: "running", stage, stage_label: stage, stages_done: plan.slice(0, idx).map(([k]) => k), done, total: 63, elapsed: t };
  },
  async cancel() { job = { status: "cancelled" }; },
  async open_result() {},
  async review_items() { return job.status === "done" || job.status === "idle" ? items : []; },
  async save_edit(id, text) { const it = items.find((i) => i.id === id); it.translation = text; it.status = "edited"; return { warnings: [], translation: text }; },
  async rebuild() { await sleep(400); return { ...result, quality: quality() }; },
  async glossary_terms(name, search) { return glossary.filter((t) => !search || t.source_term.toLowerCase().includes(search.toLowerCase())); },
  async glossary_save() { return 5; }, async glossary_delete() { return true; }, async glossary_import() { return 0; },
  async glossary_export() { return null; }, async glossary_import_terms_of_last_job() { return 3; },
  async history() {
    return { memory: 214, data_dir: "C:\\Users\\you\\AppData\\Local\\SmartBuildingTranslator", jobs: [
      { finished_at: "2026-10-02 07:42:23", file_name: "spec_ja.pdf", source_lang: "ja", target_lang: "en", model: "hy-mt2-7b", translated: 29, segments: 29, warnings: 0, seconds: 18.3 },
      { finished_at: "2026-10-01 22:39:10", file_name: "RDR_Proposal.pptx", source_lang: "en", target_lang: "ja", model: "hy-mt2-7b", translated: 87, segments: 87, warnings: 2, seconds: 89.1 }] };
  },
  async clear_history() { return { jobs: 2, memory: 214 }; },
  async system() {
    return {
      hardware: { os: "Windows 11 (10.0.26200)", cpu: "AMD Ryzen 7 5700X 8-Core Processor", cores: 16, ram_gib: 31.9,
                  gpus: [{ name: "NVIDIA GeForce RTX 4060", vram_total_mib: 8188, vram_free_mib: 7197, driver: "591.86" }] },
      recommendation: { model: "hy-mt2-7b", placement: "GPU", expectation: "Good. ~30 tok/s, 20–40 s per deck (measured on Ryzen 7 5700X + RTX 4060 8 GB, 9-slide test deck).", notes: [] },
      items: [
        { id: "engine", label: "Translation engine (llama.cpp, CUDA)", size: "0.6 GB", licence: "MIT", purpose: "Runs the translation models", source: "github.com/ggml-org/llama.cpp", installed: true, deletable: false, languages: [] },
        { id: "hy-mt2-7b", label: "Hy-MT2 7B — main translator", size: "5.9 GB", licence: "Apache-2.0", purpose: "Translates all 9 languages", source: "huggingface.co/tencent/Hy-MT2-7B-GGUF", installed: true, deletable: true, languages: ["de", "en", "es", "fr", "ja", "ko", "my", "th", "zh"] },
        { id: "qwen3-8b", label: "Qwen3 8B — repair model (optional)", size: "5.6 GB", licence: "Apache-2.0", purpose: "Re-translates paragraphs that are still flagged", source: "huggingface.co/Qwen/Qwen3-8B-GGUF", installed: true, deletable: true, languages: ["de", "en", "es", "fr", "ja", "ko", "th", "zh"] },
        { id: "ocr-ko", label: "Korean OCR (optional)", size: "13 MB", licence: "Apache-2.0", purpose: "Reads scanned Korean pages", source: "modelscope.cn/models/RapidAI/RapidOCR", installed: false, deletable: true, languages: [] }],
      download: { status: "idle" }, runtime: { path: "C:\\Users\\you\\AppData\\Local\\SmartBuildingTranslator\\runtime", custom: false, free_gb: 412.3 } };
  },
  async choose_runtime_dir() { return {}; }, async reset_runtime_dir() { return {}; },
  async setup_status() {
    await sleep(200);
    return { hardware: { cpu: "AMD Ryzen 7 5700X 8-Core Processor", cores: 16, ram_gib: 31.9,
                         gpus: [{ name: "NVIDIA GeForce RTX 4060", vram_total_mib: 8188, vram_free_mib: 7197 }] },
             recommendation: { model: "hy-mt2-7b", placement: "GPU", expectation: "Good. ~30 tok/s, 20–40 s per deck." },
             runtime: { path: "C:\\Users\\you\\AppData\\Local\\SmartBuildingTranslator\\runtime", custom: false, free_gb: 412.3 },
             installed: { ...setupInstalled }, sizes_mb: { engine: 549, "hy-mt2-7b": 5879, "qwen3-8b": 5580, "ocr-ko": 13, "ocr-th": 8 },
             settings, progress: setupProgress() };
  },
  async setup_progress() { return setupProgress(); },
  async setup_download(items) { setupRun = { kind: "download", items, t0: Date.now() }; },
  async scan_models_folder() { await sleep(300); return { path: "E:\\runtime", engine: true, components: ["hy-mt2-7b", "qwen3-8b"], usable: true, size_gb: 11.4, removable: true }; },
  async use_models_folder() { Object.assign(setupInstalled, { engine: true, "hy-mt2-7b": true, "qwen3-8b": true }); return {}; },
  async copy_models() { setupRun = { kind: "copy", items: ["engine", "hy-mt2-7b", "qwen3-8b"], t0: Date.now() }; },
  async cancel_setup() { setupRun = null; },
  async finish_setup(target) { settings = { ...settings, target_lang: target, setup_done: true }; return this.app_info(); },
  async download() {}, async download_status() { return { status: "idle" }; }, async delete_model() {},
  async get_settings() { return settings; },
  async save_settings(c) { settings = { ...settings, ...c }; return settings; },
};
