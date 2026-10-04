"""Starts the desktop window.

    SmartBuildingTranslator.exe     (installed app)
    python -m sbt ui                (development; start.bat hides the console window)
    … --selftest result.json        open the window, check page, bridge and paths, write the result, close

Offline guarantees: the network guard is installed before anything else, the page has a content security
policy that blocks every external request, and the only server involved is pywebview's own file server on
127.0.0.1 (serving the ui/ folder).
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from sbt.privacy import network_guard
from sbt.settings import FROZEN, PROJECT_ROOT, data_dir, runtime_dir

UI_DIR = PROJECT_ROOT / "ui"
_STARTED = time.time()
log = logging.getLogger("sbt.ui")


def _setup_logging() -> None:
    """Log file in the user's data folder. Counts and error types only — never document text."""
    folder = data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "app.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    for noisy in ("httpx", "pywebview"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _register_drop(window) -> None:  # type: ignore[no-untyped-def]
    """Files dropped onto the window: the page cannot see file paths, so Python reads the real path and hands
    it to the page."""
    from webview.dom import DOMEventHandler

    def on_drop(event: dict) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if paths:
            window.evaluate_js(f"window.sbtFileDropped && window.sbtFileDropped({json.dumps(paths[0])})")

    def ignore(_: dict) -> None:
        pass

    doc = window.dom.document
    doc.events.dragenter += DOMEventHandler(ignore, True, True)
    doc.events.dragover += DOMEventHandler(ignore, True, True, debounce=500)
    doc.events.drop += DOMEventHandler(on_drop, True, True)


def _selftest_translation(api, document: Path) -> dict[str, object]:  # type: ignore[no-untyped-def]
    """The app's own translation path (job thread, engine, quality checks, Review, page pictures)."""
    info = api.inspect_file(str(document))
    api.start_translation({"path": str(document), "source": info["detected"], "target": info["target"],
                           "memory": False})
    deadline = time.time() + 900
    status = api.job_status()
    while status["status"] == "running" and time.time() < deadline:
        time.sleep(1)
        status = api.job_status()
    out: dict[str, object] = {"status": status["status"], "error": status.get("error", ""),
                              "stages": status.get("stages_done")}
    result = status.get("result") or {}
    if result:
        summary = result["quality"]["summary"]
        out.update({"segments": result["segments"], "translated_pct": result["translated_pct"],
                    "output_written": Path(result["output"]).exists(),
                    "quality": {k: (v["errors"], v["warnings"]) for k, v in summary.items()},
                    "review_items": len(api.review_items())})
        view = api.page_view(1)
        out["page_view"] = {"available": view["available"], "reason": view.get("reason", ""),
                            "has_pictures": str(view.get("translated", "")).startswith("data:image/png")}
    return out


def _selftest(window, api, result: Path, document: Path | None = None) -> None:  # type: ignore[no-untyped-def]
    """Checks a packaged build without a person at the screen: page rendered, JavaScript bridge, paths and,
    with a document, a complete translation through the app."""
    from sbt import __version__
    report: dict[str, object] = {"version": __version__, "frozen": FROZEN, "ui_dir": str(UI_DIR),
                                 "runtime_dir": str(runtime_dir()), "data_dir": str(data_dir())}
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                ready = window.evaluate_js("!!(window.pywebview && window.pywebview.api && "
                                           "document.querySelector('.drop, .setup-steps'))")
            except Exception:  # noqa: BLE001 - page not ready yet
                ready = False
            if ready:
                break
            time.sleep(0.5)
        report["ready_seconds"] = round(time.time() - _STARTED, 1)       # start → page usable
        report["page_rendered"] = bool(window.evaluate_js("!!document.querySelector('.drop, .setup-steps')"))
        report["screen"] = window.evaluate_js("location.hash")       # #setup on a first start without models
        report["bridge_functions"] = window.evaluate_js("Object.keys(window.pywebview.api).length")
        report["page_title"] = window.evaluate_js("document.title")
        info = api.app_info()
        report.update({k: info[k] for k in ("engine_installed", "model_installed", "mode")})
        report["languages"] = len(info["languages"])  # type: ignore[arg-type]
        report["ok"] = bool(report["page_rendered"]) and int(report["bridge_functions"] or 0) > 20  # type: ignore[call-overload]
        if document is not None:
            window.evaluate_js("location.hash = '#translate'; 1")
            report["translation"] = translation = _selftest_translation(api, document)
            report["ok"] = report["ok"] and translation["status"] == "done" and bool(translation.get("output_written"))
    except Exception as e:  # noqa: BLE001 - reported, not raised
        report["ok"] = False
        report["error"] = f"{type(e).__name__}: {e}"
    result.write_text(json.dumps(report, indent=2), encoding="utf-8")
    window.destroy()


def main(debug: bool = False, selftest: Path | None = None, selftest_document: Path | None = None) -> int:
    network_guard.install()
    _setup_logging()
    import webview

    from sbt.ui import pages
    from sbt.ui.api import Api
    pages.clear_cache()                 # page pictures contain document content: none survive a session
    api = Api()
    window = webview.create_window("Smart Building Translator", str(UI_DIR / "index.html"), js_api=api,
                                   width=1240, height=820, min_size=(900, 620), background_color="#f4f6f9")
    api._window = window
    window.events.loaded += lambda: _register_drop(window)
    if selftest is not None:
        threading.Thread(target=_selftest, args=(window, api, selftest, selftest_document), daemon=True).start()
    log.info("UI started")
    try:
        webview.start(debug=debug, private_mode=True)
    finally:
        pages.clear_cache()
    log.info("UI closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
