"""Writes the user's settings file (%LOCALAPPDATA%\\SmartBuildingTranslator\\settings.toml) from the Settings screen."""
from __future__ import annotations

from pathlib import Path

from sbt import settings as settings_mod
from sbt.languages import LANGUAGES

EDITABLE = {
    "use_memory": bool,       # keep a translation memory on this PC
    "repair_model": str,      # "qwen3-8b" or "" (off)
    "gpu": str,               # auto | cpu
    "doc_terms": str,         # vote | off
    "glossary": str,          # default glossary
    "theme": str,             # system | light | dark (UI only)
    "runtime_dir": str,       # folder with the engine and models ("" = default)
    "target_lang": str,       # usual target language ("" = automatic)
    "setup_done": bool,       # first-start setup guide completed
}
ALLOWED = {"gpu": {"auto", "cpu"}, "doc_terms": {"vote", "off", "hint", "enforce"},
           "theme": {"system", "light", "dark"}, "repair_model": {"", "qwen3-8b"},
           "target_lang": {"", *LANGUAGES}}


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def current() -> dict[str, object]:
    s = settings_mod.load()
    values = {k: getattr(s, k) for k in EDITABLE if hasattr(s, k)}
    values["theme"] = s.extra.get("theme", "system")
    return values


def save(changes: dict[str, object]) -> dict[str, object]:
    values = current()
    for key, value in changes.items():
        if key not in EDITABLE:
            raise ValueError(f"Unknown setting: {key}")
        value = EDITABLE[key](value)
        if key in ALLOWED and value not in ALLOWED[key]:
            raise ValueError(f"Invalid value for {key}")
        if key == "runtime_dir" and value and not Path(str(value)).is_dir():
            raise ValueError("The models folder does not exist.")
        values[key] = value
    path = settings_mod.data_dir() / "settings.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Written by the Smart Building Translator settings screen. Keys: see config/default.toml."]
    lines += [f"{k} = {_toml_value(v)}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    settings_mod.load()                 # validate what was written
    return values
