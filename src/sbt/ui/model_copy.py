"""Models from a folder or USB stick (setup guide): find them, and copy them to this PC.

Every model file is checked against the SHA-256 published by its source while it is copied (a damaged or
different file is deleted again); the engine's program files are scanned by Windows Defender after copying —
the same checks as a download.
"""
from __future__ import annotations

import ctypes
import hashlib
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from sbt.download import ASSETS, defender_scan

# relative path in the models folder → (component, SHA-256) for every file with a published fingerprint
KNOWN = {a.dest: (a.name, a.sha256) for a in ASSETS if a.unzip_to is None}
MAIN_MODEL = next(dest for dest, (name, _) in KNOWN.items() if name == "hy-mt2-7b")
ENGINE = "llama/llama-server.exe"
CHUNK = 8 << 20


def resolve(folder: Path) -> Path:
    """Accept the models folder itself, or a folder that contains it (the project folder, a USB stick root)."""
    for candidate in (folder, folder / "runtime", folder / "SmartBuildingTranslator" / "runtime"):
        if (candidate / "llama").is_dir() or (candidate / "models").is_dir():
            return candidate
    return folder


def removable(path: Path) -> bool:
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(str(Path(path).anchor)) == 2   # DRIVE_REMOVABLE
    except (AttributeError, OSError):
        return False


def _files(folder: Path) -> list[Path]:
    """What a models folder needs: the engine folder, and the model / OCR files this app knows."""
    files = [f for f in (folder / "llama").rglob("*") if f.is_file()] if (folder / "llama").is_dir() else []
    files += [folder / rel for rel in KNOWN if (folder / rel).is_file()]
    return files


def scan(folder: Path) -> dict[str, object]:
    folder = resolve(Path(folder))
    files = _files(folder)
    present = [KNOWN[rel][0] for rel in KNOWN if (folder / rel).is_file()]
    engine = (folder / ENGINE).is_file()
    return {"path": str(folder), "engine": engine, "components": present,
            "usable": engine and (folder / MAIN_MODEL).is_file(),
            "size_gb": round(sum(f.stat().st_size for f in files) / 2**30, 1), "removable": removable(folder)}


@dataclass
class CopyState:
    status: str = "idle"           # idle | running | done | failed | cancelled
    file: str = ""
    percent: int = 0
    copied_mb: int = 0
    total_mb: int = 0
    verified: list[str] = field(default_factory=list)
    message: str = ""


class Copier:
    def __init__(self) -> None:
        self.state = CopyState()
        self._cancel = threading.Event()

    def start(self, source: Path, target: Path, on_done=None) -> None:  # type: ignore[no-untyped-def]
        if self.state.status == "running":
            raise RuntimeError("Copying is already running")
        source, target = resolve(Path(source)), Path(target)
        if source.resolve() == target.resolve():
            raise ValueError("The models are already in this folder.")
        files = _files(source)
        if not files:
            raise ValueError("No translation engine or models were found in that folder.")
        self._cancel.clear()
        self.state = CopyState(status="running", total_mb=max(1, sum(f.stat().st_size for f in files) >> 20))
        threading.Thread(target=self._run, args=(source, target, files, on_done), daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, source: Path, target: Path, files: list[Path], on_done) -> None:  # type: ignore[no-untyped-def]
        copied = 0
        part: Path | None = None
        try:
            for f in files:
                rel = f.relative_to(source).as_posix()
                self.state.file = rel
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_name(dest.name + ".copying")
                digest = hashlib.sha256()
                with f.open("rb") as src, part.open("wb") as out:
                    while chunk := src.read(CHUNK):
                        if self._cancel.is_set():
                            raise InterruptedError
                        out.write(chunk)
                        digest.update(chunk)
                        copied += len(chunk)
                        self.state.copied_mb = copied >> 20
                        self.state.percent = min(99, self.state.copied_mb * 100 // self.state.total_mb)
                if rel in KNOWN:
                    name, expected = KNOWN[rel]
                    if digest.hexdigest() != expected:
                        part.unlink(missing_ok=True)
                        raise ValueError(f"{dest.name} is damaged or not the expected file (fingerprint does not "
                                         "match). Copy it again from the original source, or download it.")
                    self.state.verified.append(name)
                part.replace(dest)
                part = None
            if (target / "llama").is_dir():
                self.state.file = "virus scan of the engine"
                found = defender_scan(target / "llama")
                if found:
                    shutil.rmtree(target / "llama", ignore_errors=True)
                    raise ValueError("Windows Defender reported a problem in the engine files; they were removed.")
            self.state.status, self.state.percent, self.state.message = "done", 100, "Copied and verified"
            if on_done is not None:
                on_done(target)
        except InterruptedError:
            self.state.status, self.state.message = "cancelled", "Copying cancelled"
        except (OSError, ValueError) as e:
            self.state.status = "failed"
            self.state.message = str(e) if isinstance(e, ValueError) else f"Copying failed: {e.strerror or e}"
        finally:
            if part is not None:                 # the file being copied when it stopped
                part.unlink(missing_ok=True)
