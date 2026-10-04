"""Packaging: where the app finds its files when installed, and how it starts the downloader."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sbt import download, settings
from sbt.ui import downloads, settings_store


@pytest.fixture()
def data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SBT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SBT_RUNTIME_DIR", raising=False)
    return tmp_path


def test_runtime_folder_default_override_and_setting(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert settings.runtime_dir() == settings.PROJECT_ROOT / "runtime"          # development
    monkeypatch.setattr(settings, "FROZEN", True)
    assert settings.runtime_dir() == data / "data" / "runtime"                 # installed app: user data folder
    chosen = data / "models from old PC"
    chosen.mkdir()
    settings_store.save({"runtime_dir": str(chosen)})
    assert settings.runtime_dir() == chosen                                     # a folder chosen in Models
    monkeypatch.setenv("SBT_RUNTIME_DIR", str(data / "env"))
    assert settings.runtime_dir() == data / "env"                              # explicit override wins
    settings_store.save({"runtime_dir": ""})
    monkeypatch.delenv("SBT_RUNTIME_DIR")
    assert settings.runtime_dir() == data / "data" / "runtime"


def test_models_folder_must_exist(data: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        settings_store.save({"runtime_dir": str(data / "missing")})


def test_downloader_runs_in_its_own_process(monkeypatch: pytest.MonkeyPatch) -> None:
    assert downloads.command(("hy-mt2-7b",))[:4] == [sys.executable, "-u", "-m", "sbt"]
    monkeypatch.setattr(downloads, "FROZEN", True)
    cmd = downloads.command(("llama-cuda", "cudart"))
    assert Path(cmd[0]).name == "sbt.exe" and cmd[1:] == ["download", "--only", "llama-cuda", "cudart"]


def test_download_targets_are_inside_the_runtime_folder(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert download.run(["no-such-model"], tmp_path) == 2
    assert "Known:" in capsys.readouterr().out
    for asset in download.ASSETS:
        assert not Path(asset.dest).is_absolute() and ".." not in Path(asset.dest).parts


def test_installed_components_follow_the_models_folder(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = data / "rt"
    (folder / "llama").mkdir(parents=True)
    monkeypatch.setenv("SBT_RUNTIME_DIR", str(folder))
    assert not downloads.installed("engine")
    (folder / "llama" / "llama-server.exe").write_bytes(b"")
    assert downloads.installed("engine")


def test_settings_file_saved_by_notepad_is_accepted(data: Path) -> None:
    """Notepad and PowerShell 5 write UTF-8 with a byte-order mark; the settings file must still load."""
    folder = data / "models"
    folder.mkdir()
    (data / "data").mkdir(parents=True, exist_ok=True)
    (data / "data" / "settings.toml").write_text(f"runtime_dir = '{folder}'\ngpu = \"cpu\"\n", encoding="utf-8-sig")
    assert settings.load().gpu == "cpu"
    assert settings.runtime_dir() == folder
