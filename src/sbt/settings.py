"""Application settings: project defaults (config/default.toml) overlaid with the user's own settings file.

User data (database with glossary, translation memory and job history) lives in the Windows user profile, not
in the project folder, so copying or uploading the project never carries document content along.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

# Packaged app (PyInstaller): read-only files that ship with the app (ui/, config/, data/) are in the app folder's
# _internal directory; in development they are in the project folder.
FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
DEFAULTS_FILE = PROJECT_ROOT / "config" / "default.toml"


def data_dir() -> Path:
    """%LOCALAPPDATA%\\SmartBuildingTranslator, overridable with SBT_DATA_DIR (used by tests)."""
    override = os.environ.get("SBT_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "SmartBuildingTranslator"


def runtime_dir() -> Path:
    """Translation engine, models and OCR models (large; written by the downloader).

    SBT_RUNTIME_DIR, else the user's `runtime_dir` setting (e.g. a folder copied from another PC), else
    %LOCALAPPDATA%\\SmartBuildingTranslator\\runtime for the installed app, or <project>\\runtime in development.
    """
    override = os.environ.get("SBT_RUNTIME_DIR")
    if override:
        return Path(override)
    user = data_dir() / "settings.toml"
    if user.exists():
        try:
            chosen = _flatten(tomllib.loads(user.read_text(encoding="utf-8-sig"))).get("runtime_dir")
        except (tomllib.TOMLDecodeError, OSError):
            chosen = None
        if chosen:
            return Path(str(chosen))
    return data_dir() / "runtime" if FROZEN else PROJECT_ROOT / "runtime"


@dataclass
class Settings:
    mode: str = "offline"                     # online mode is not implemented; see PRIVACY.md
    model: str = "hy-mt2-7b"
    repair_model: str = "qwen3-8b"            # second engine for still-flagged segments ("" = off)
    glossary: str = "smart-building"
    use_memory: bool = True                   # store/reuse translations locally (contains document text)
    doc_terms: str = "vote"                   # document term sheet: off | vote | hint | enforce
    gpu: str = "auto"                         # auto | cpu
    min_font_scale: float = 0.8
    protect: str = "verify"
    runtime_dir: str = ""                     # folder with llama/ and models/ ("" = default, see runtime_dir())
    target_lang: str = ""                     # usual target language ("" = automatic: en→ja, ja→en, others→en)
    setup_done: bool = False                  # the first-start setup guide was completed
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return data_dir() / "sbt.db"

    @property
    def user_file(self) -> Path:
        return data_dir() / "settings.toml"


def _flatten(raw: dict[str, object]) -> dict[str, object]:
    """Accept both flat keys and the sectioned layout of config/default.toml."""
    flat: dict[str, object] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def load() -> Settings:
    known = {f.name for f in fields(Settings)} - {"extra"}
    merged: dict[str, object] = {}
    for path in (DEFAULTS_FILE, data_dir() / "settings.toml"):
        if path.exists():
            merged.update(_flatten(tomllib.loads(path.read_text(encoding="utf-8-sig"))))
    s = Settings(**{k: v for k, v in merged.items() if k in known})  # type: ignore[arg-type]
    s.extra = {k: v for k, v in merged.items() if k not in known}
    if s.mode != "offline":
        raise ValueError("Only offline mode exists in this version. Set mode = \"offline\" in settings.toml.")
    if s.doc_terms not in ("off", "vote", "hint", "enforce"):
        raise ValueError("doc_terms must be off, vote, hint or enforce")
    from sbt.languages import LANGUAGES
    if s.target_lang and s.target_lang not in LANGUAGES:
        raise ValueError(f"target_lang must be one of {', '.join(LANGUAGES)} (or empty for automatic)")
    return s
