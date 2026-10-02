"""Starts the desktop window.

    python -m sbt ui        (or start.bat, which hides the console window)

Offline guarantees: the network guard is installed before anything else, the page has a content security
policy that blocks every external request, and the only server involved is pywebview's own file server on
127.0.0.1 (serving the ui/ folder).
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler

from sbt.privacy import network_guard
from sbt.settings import PROJECT_ROOT, data_dir

UI_DIR = PROJECT_ROOT / "ui"
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


def main(debug: bool = False) -> int:
    network_guard.install()
    _setup_logging()
    import webview

    from sbt.ui.api import Api
    api = Api()
    window = webview.create_window("Smart Building Translator", str(UI_DIR / "index.html"), js_api=api,
                                   width=1240, height=820, min_size=(900, 620), background_color="#f4f6f9")
    api._window = window
    window.events.loaded += lambda: _register_drop(window)
    log.info("UI started")
    webview.start(debug=debug, private_mode=True)
    log.info("UI closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
