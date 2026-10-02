// Fake API with sample data, for working on the UI in a normal browser (index.html?mock). Not used by the app.
const languages = [["en", "English"], ["ja", "Japanese"], ["zh", "Chinese"], ["ko", "Korean"], ["my", "Burmese"],
  ["th", "Thai"], ["de", "German"], ["fr", "French"], ["es", "Spanish"]].map(([code, name]) => ({ code, name }));
let settings = { use_memory: true, repair_model: "qwen3-8b", gpu: "auto", doc_terms: "vote", glossary: "smart-building", theme: "system" };
let job = { status: "idle" };
let t0 = 0;
let items = [
  { id: "s1/2/p0", page: 1, kind: "title", status: "translated", problems: [], problem_text: [], flagged: false, ocr: false, has_tags: false,
    source: "Smart Building Platform Overview", translation: "スマートビルディングプラットフォーム概要" },
  { id: "s2/3/p0", page: 2, kind: "body", status: "translated", problems: [], problem_text: [], flagged: false, ocr: false, has_tags: true,
    source: "The [1]Building Management System[/1] monitors and controls HVAC equipment.", translation: "[1]ビル管理システム[/1]は、HVAC機器の監視および制御を行います。" },
  { id: "s2/3/p2", page: 2, kind: "body", status: "retried", problems: ["term_missing"], problem_text: ["a required glossary term is missing"], flagged: true, ocr: false, has_tags: false,
    source: "Variable Air Volume (VAV) terminal control", translation: "可変風量（VAV）端子制御" },
  { id: "s5/3/t1.3/p0", page: 5, kind: "table_cell", status: "kept", problems: [], problem_text: [], flagged: false, ocr: false, has_tags: false,
    source: "47808", translation: "47808" },
  { id: "s8/3/p0", page: 8, kind: "body", status: "translated", problems: [], problem_text: [], flagged: false, ocr: false, has_tags: false,
    source: "When a chiller alarm occurs, the system automatically notifies the maintenance team by e-mail and creates a work order.",
    translation: "冷凍機の警報が発生すると、システムは自動的にメールで保守チームに通知し、作業指示を作成します。" },
];
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
  warnings: [{ count: 1, text: "text may not fit its box even after shrinking", code: "overflow" }],
  font_reduced: 2, not_translatable: [{ count: 1, text: "picture contains text (not translated)" }], notices: [],
  ocr_segments: 0, doc_terms: 3, doc_terms_unresolved: 1, repaired: 1, edited: 0, flagged: 1,
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export const mockApi = {
  async app_info() {
    return { version: "0.4.0", mode: "offline", languages, glossaries: ["smart-building"], settings, engine_installed: true,
             model_installed: true, data_dir: "C:\\Users\\you\\AppData\\Local\\SmartBuildingTranslator" };
  },
  async choose_file() { return "D:\\Work\\Projects\\Building_System_Overview.pptx"; },
  async inspect_file(path) {
    await sleep(300);
    return { path, name: path.split("\\").pop(), folder: "D:\\Work\\Projects", type: path.endsWith(".pdf") ? "PDF" : "PPTX",
             size_kb: 1280, pages: 9, paragraphs: 63, detected: "en", confidence: 1, target: "ja", notes: [] };
  },
  async start_translation() { job = { status: "running", stage: "read", stages_done: [], done: 0, total: 63 }; t0 = Date.now(); return {}; },
  async job_status() {
    if (job.status !== "running") return job;
    const t = (Date.now() - t0) / 1000;
    const plan = [["read", 0.8], ["load", 2], ["terms", 3], ["translate", 8], ["align", 8.8], ["write", 9.6]];
    const idx = plan.findIndex(([, end]) => t < end);
    if (idx === -1) { job = { status: "done", stage: "write", stages_done: plan.map(([k]) => k), done: 63, total: 63, elapsed: t, result }; return job; }
    const stage = plan[idx][0];
    const done = stage === "translate" ? Math.round(63 * (t - 3) / 5) : stage === "align" || stage === "write" ? 63 : 0;
    return { status: "running", stage, stage_label: stage, stages_done: plan.slice(0, idx).map(([k]) => k), done, total: 63, elapsed: t };
  },
  async cancel() { job = { status: "cancelled" }; },
  async open_result() {},
  async review_items() { return job.status === "done" || job.status === "idle" ? items : []; },
  async save_edit(id, text) { const it = items.find((i) => i.id === id); it.translation = text; it.status = "edited"; return { warnings: [], translation: text }; },
  async rebuild() { await sleep(400); return result; },
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
      download: { status: "idle" } };
  },
  async download() {}, async download_status() { return { status: "idle" }; }, async delete_model() {},
  async get_settings() { return settings; },
  async save_settings(c) { settings = { ...settings, ...c }; return settings; },
};
