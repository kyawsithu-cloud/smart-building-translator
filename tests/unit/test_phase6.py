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


# --- setup guide ---------------------------------------------------------------------------------------------
def test_usual_target_language(data: Path) -> None:
    from sbt import langdetect
    assert langdetect.default_target("en") == "ja" and langdetect.default_target("ja") == "en"
    assert langdetect.default_target("en", "zh") == "zh"
    assert langdetect.default_target("zh", "zh") == "en"           # never translate a document into itself
    settings_store.save({"target_lang": "ko"})
    assert settings.load().target_lang == "ko"
    with pytest.raises(ValueError):
        settings_store.save({"target_lang": "xx"})


def test_opened_file_gets_the_usual_target_language(data: Path) -> None:
    from sbt.ui.api import Api
    from tests.unit.test_phase4 import _deck
    deck = _deck(data / "deck.pptx")
    api = Api()
    assert api.inspect_file(str(deck))["target"] == "ja"
    info = api.finish_setup("zh")
    assert info["setup_done"] is True and info["settings"]["target_lang"] == "zh"
    assert api.inspect_file(str(deck))["target"] == "zh"


def _fake_runtime(root: Path, model_bytes: bytes = b"weights") -> Path:
    (root / "llama").mkdir(parents=True)
    (root / "llama" / "llama-server.exe").write_bytes(b"engine")
    (root / "llama" / "ggml.dll").write_bytes(b"library")
    (root / "models").mkdir()
    (root / "models" / "HY-MT2-7B-Q6_K.gguf").write_bytes(model_bytes)
    return root


def test_models_folder_scan_accepts_the_folder_that_contains_it(tmp_path: Path) -> None:
    from sbt.ui import model_copy
    _fake_runtime(tmp_path / "stick" / "runtime")
    found = model_copy.scan(tmp_path / "stick")
    assert found["path"] == str(tmp_path / "stick" / "runtime")
    assert found["usable"] and found["engine"] and found["components"] == ["hy-mt2-7b"]
    assert not model_copy.scan(tmp_path / "empty")["usable"]


def _copy(monkeypatch: pytest.MonkeyPatch, source: Path, target: Path, published: str):  # type: ignore[no-untyped-def]
    import hashlib
    import time

    from sbt.ui import model_copy
    monkeypatch.setattr(model_copy, "KNOWN", {"models/HY-MT2-7B-Q6_K.gguf": ("hy-mt2-7b", published)})
    monkeypatch.setattr(model_copy, "defender_scan", lambda folder: "")
    copier = model_copy.Copier()
    copier.start(source, target)
    deadline = time.time() + 30
    while copier.state.status == "running" and time.time() < deadline:
        time.sleep(0.05)
    return copier.state, hashlib


def test_copy_from_a_usb_stick_is_verified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    source = _fake_runtime(tmp_path / "stick")
    state, _ = _copy(monkeypatch, source, tmp_path / "pc", hashlib.sha256(b"weights").hexdigest())
    assert state.status == "done" and state.verified == ["hy-mt2-7b"]
    assert (tmp_path / "pc" / "llama" / "ggml.dll").read_bytes() == b"library"
    assert (tmp_path / "pc" / "models" / "HY-MT2-7B-Q6_K.gguf").read_bytes() == b"weights"


def test_damaged_model_file_is_not_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    source = _fake_runtime(tmp_path / "stick", b"weights, but damaged")
    state, _ = _copy(monkeypatch, source, tmp_path / "pc", hashlib.sha256(b"weights").hexdigest())
    assert state.status == "failed" and "fingerprint" in state.message
    assert not (tmp_path / "pc" / "models" / "HY-MT2-7B-Q6_K.gguf").exists()
    assert not list((tmp_path / "pc").rglob("*.copying"))


def test_one_progress_bar_for_several_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeProcess:
        stdout = iter(["Downloading to the models folder\n", "[llama-cuda] 100% of 145 MB\n", "[llama-cuda] SHA-256 verified\n",
                       "[hy-mt2-7b] 50% of 5879 MB\n"])

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(downloads.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(downloads.threading, "Thread", lambda target, daemon: type("T", (), {"start": lambda self: None})())
    d = downloads.Downloader()
    d.start_assets(("llama-cuda", "hy-mt2-7b"), "setup")
    d._follow()
    assert d.state.finished == ["llama-cuda"] and d.state.status == "done" and d.state.overall == 100
    assert d.state.total_mb == 145 + 5879
