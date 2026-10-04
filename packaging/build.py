"""Builds the Windows app: dist/SmartBuildingTranslator/ (+ portable zip, + Setup.exe when Inno Setup is installed).

    .venv\\Scripts\\python -m pip install -e .[build]
    .venv\\Scripts\\python packaging\\build.py            # build, scan, test, package

Steps: version resource → PyInstaller (packaging/SmartBuildingTranslator.spec) → licence notices → Windows Defender
scan → smoke tests of the built programs (offline; uses the existing models folder when there is one) → portable
zip → installer (packaging/installer.iss, needs Inno Setup 6) → SHA-256 of the results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sbt import __version__ as VERSION

PKG, BUILD, DIST = ROOT / "packaging", ROOT / "build", ROOT / "dist"
APP = DIST / "SmartBuildingTranslator"
DEFENDER = Path(r"C:\Program Files\Windows Defender\MpCmdRun.exe")
ISCC = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), ROOT / "runtime" / "tools" / "InnoSetup" / "ISCC.exe"]


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def version_file() -> None:
    nums = tuple(int(x) for x in VERSION.split(".")) + (0,)
    strings = {"CompanyName": "", "FileDescription": "Smart Building Translator", "FileVersion": VERSION,
               "InternalName": "SmartBuildingTranslator", "LegalCopyright": "Copyright (c) 2026 kyawsithu-cloud, MIT",
               "OriginalFilename": "SmartBuildingTranslator.exe", "ProductName": "Smart Building Translator",
               "ProductVersion": VERSION}
    table = ", ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    BUILD.mkdir(exist_ok=True)
    (BUILD / "version_info.txt").write_text(
        f"VSVersionInfo(ffi=FixedFileInfo(filevers={nums[:4]}, prodvers={nums[:4]}, mask=0x3f, flags=0x0, "
        f"OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo([StringTable('040904B0', "
        f"[{table}])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n", encoding="utf-8")


def pyinstaller() -> None:
    if not (PKG / "app.ico").exists():
        subprocess.run([sys.executable, str(PKG / "make_icon.py")], check=True)
    shutil.rmtree(APP, ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", str(PKG / "SmartBuildingTranslator.spec"), "--noconfirm",
                    "--clean", "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"), "--log-level", "WARN"],
                   check=True, cwd=ROOT)


def _requirements(name: str, seen: set[str]) -> None:
    key = re.sub(r"[-_.]+", "-", name).lower()
    if key in seen:
        return
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return
    seen.add(key)
    for req in dist.requires or []:
        if "extra ==" in req:
            continue
        if ";" in req and "sys_platform" in req and "win32" not in req:
            continue
        _requirements(re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0], seen)


def licences() -> None:
    """THIRD_PARTY_LICENSES.txt: every library inside the app, its version, licence and licence text."""
    import tomllib
    names: set[str] = set()
    # pyproject.toml, not the installed metadata (an editable install keeps the dependency list it was installed with)
    for req in tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]:
        _requirements(re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0], names)
    parts = [f"Smart Building Translator {VERSION} — third-party software included in this application\n",
             "Python (PSF License) — https://www.python.org/\n",
             ("IMPORTANT: PyMuPDF / MuPDF are licensed under the GNU AGPL-3.0. If you give this application to "
              "others, the AGPL applies to the whole program: make its complete source code available to them "
              "(see README.md, Licence). Source of PyMuPDF: https://github.com/pymupdf/PyMuPDF\n"),
             ("Not included, downloaded separately on request: llama.cpp (MIT), Hy-MT2 and Qwen3 models "
              "(Apache-2.0), optional OCR models (Apache-2.0). Microsoft Edge WebView2 is part of Windows.\n")]
    for name in sorted(names):
        dist = metadata.distribution(name)
        meta = dist.metadata
        lic = meta.get("License-Expression") or meta.get("License") or ", ".join(
            c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::"))
        url = meta.get("Home-page") or next((u.split(",", 1)[-1].strip() for u in meta.get_all("Project-URL") or []), "")
        parts.append("=" * 100 + f"\n{meta['Name']} {dist.version}\nLicence: {(lic or 'see below').splitlines()[0][:200]}\n{url}\n")
        for f in dist.files or []:
            if re.search(r"(LICEN[CS]E|COPYING|NOTICE)", f.name, re.IGNORECASE) and f.suffix.lower() in ("", ".txt", ".md", ".rst"):
                try:
                    parts.append(f"--- {f.name} ---\n{(dist.locate_file(f)).read_text(encoding='utf-8', errors='replace').strip()}\n")
                except OSError:
                    pass
    (APP / "THIRD_PARTY_LICENSES.txt").write_text("\n".join(parts), encoding="utf-8")
    shutil.copy(ROOT / "LICENSE", APP / "LICENSE.txt")


def defender(path: Path) -> None:
    if not DEFENDER.exists():
        print("  Windows Defender command line not found: scan skipped")
        return
    r = subprocess.run([str(DEFENDER), "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"],
                       capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise SystemExit(f"Windows Defender reported a problem in {path}:\n{r.stdout}\n{r.stderr}")
    print(f"  Windows Defender: no threats found in {path.name}")


def smoke_tests() -> dict[str, object]:
    """Runs the built programs with a throw-away data folder, offline. A translation is tested only when an
    installed models folder exists (development PC); it is never downloaded here."""
    results: dict[str, object] = {}
    tmp = Path(tempfile.mkdtemp(prefix="sbt_build_test_"))
    env = {**os.environ, "SBT_DATA_DIR": str(tmp / "data")}
    sbt = APP / "sbt.exe"
    out = subprocess.run([str(sbt), "doctor"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
                         check=False)
    results["doctor"] = out.returncode == 0 and "Recommendation" in out.stdout
    print(f"  sbt.exe doctor: {'OK' if results['doctor'] else 'FAILED'}")
    if not results["doctor"]:
        print(out.stdout[-2000:], out.stderr[-2000:])
    selftest = tmp / "selftest.json"
    subprocess.run([str(APP / "SmartBuildingTranslator.exe"), "--selftest", str(selftest)], env=env, timeout=180,
                   check=False)
    report = json.loads(selftest.read_text(encoding="utf-8")) if selftest.exists() else {"ok": False}
    results["window"] = report
    print(f"  SmartBuildingTranslator.exe self-test: {'OK' if report.get('ok') else 'FAILED'} {report}")
    models = ROOT / "runtime"
    if (models / "llama" / "llama-server.exe").exists():
        deck = tmp / "app_sample_en.pptx"
        shutil.copy(ROOT / "eval" / "testset" / "sample_en.pptx", deck)
        selftest = tmp / "selftest_translate.json"
        subprocess.run([str(APP / "SmartBuildingTranslator.exe"), "--selftest", str(selftest),
                        "--selftest-document", str(deck)], env={**env, "SBT_RUNTIME_DIR": str(models)}, timeout=1200,
                       check=False)
        report = json.loads(selftest.read_text(encoding="utf-8")) if selftest.exists() else {"ok": False}
        results["window_translation"] = report
        print(f"  SmartBuildingTranslator.exe translates through the window: {'OK' if report.get('ok') else 'FAILED'} "
              f"{report.get('translation')}")
        deck = tmp / "rich_en.pptx"
        shutil.copy(ROOT / "eval" / "testset" / "rich_en.pptx", deck)
        out = subprocess.run([str(sbt), "translate", str(deck), "--no-memory"], capture_output=True, text=True,
                             encoding="utf-8", env={**env, "SBT_RUNTIME_DIR": str(models)}, timeout=900, check=False)
        written = (tmp / "rich_en_JA.pptx").exists()
        results["translate"] = out.returncode == 0 and written
        print(f"  sbt.exe translate (public test deck, existing models folder): "
              f"{'OK' if results['translate'] else 'FAILED'}")
        print("\n".join("    " + ln for ln in out.stdout.splitlines()[-9:]))
        scanned = tmp / "spec_en_scanned.pdf"
        shutil.copy(ROOT / "eval" / "testset" / "spec_en_scanned.pdf", scanned)
        out = subprocess.run([str(sbt), "check", str(ROOT / "eval" / "testset" / "sample_en.pptx"),
                              str(ROOT / "eval" / "results" / "phase3" / "hy-mt2-7b" / "sample_en_en-ja_vote.pptx"),
                              "--no-model"], capture_output=True, text=True, encoding="utf-8", env=env, timeout=300,
                             check=False)
        results["check"] = out.returncode == 0 and "Terminology consistency" in out.stdout
        print(f"  sbt.exe check: {'OK' if results['check'] else 'FAILED'}")
        out = subprocess.run([str(sbt), "translate", str(scanned), "--no-memory"], capture_output=True, text=True,
                             encoding="utf-8", env={**env, "SBT_RUNTIME_DIR": str(models)}, timeout=900, check=False)
        results["scanned_pdf_ocr"] = out.returncode == 0 and "OCR" in out.stdout
        print(f"  sbt.exe translate scanned PDF (OCR inside the app): {'OK' if results['scanned_pdf_ocr'] else 'FAILED'}")
    for f in (ROOT / "eval" / "results" / "phase3" / "hy-mt2-7b").glob("sample_en_en-ja_vote.checks.csv"):
        f.unlink()                                          # written by the check test above
    shutil.rmtree(tmp, ignore_errors=True)
    return results


def portable_zip() -> Path:
    target = DIST / f"SmartBuildingTranslator-{VERSION}-portable.zip"
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in APP.rglob("*"):
            z.write(f, Path("SmartBuildingTranslator") / f.relative_to(APP))
    return target


def installer() -> Path | None:
    iscc = next((p for p in ISCC if p.exists()), None)
    if iscc is None:
        print("  Inno Setup 6 not found: installer skipped (see DEVELOPMENT.md)")
        return None
    subprocess.run([str(iscc), "/Q", f"/DAppVersion={VERSION}", f"/O{DIST}", str(PKG / "installer.iss")], check=True)
    return DIST / f"SmartBuildingTranslator-{VERSION}-Setup.exe"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--no-tests", action="store_true")
    p.add_argument("--no-installer", action="store_true")
    args = p.parse_args()
    step(f"Building Smart Building Translator {VERSION}")
    version_file()
    pyinstaller()
    licences()
    size = sum(f.stat().st_size for f in APP.rglob("*") if f.is_file())
    print(f"  {APP} — {size / 2**20:.0f} MB, {sum(1 for _ in APP.rglob('*'))} files")
    step("Virus scan")
    defender(APP)
    results: dict[str, object] = {}
    if not args.no_tests:
        step("Smoke tests (offline)")
        results = smoke_tests()
    step("Packages")
    artefacts = [portable_zip()]
    if not args.no_installer:
        setup = installer()
        if setup is not None:
            defender(setup)
            artefacts.append(setup)
    lines = [f"{a.name}  {a.stat().st_size / 2**20:.0f} MB  SHA-256 {sha256(a)}" for a in artefacts]
    (DIST / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join("  " + ln for ln in lines))
    failed = [k for k, v in results.items() if not (v.get("ok") if isinstance(v, dict) else v)]
    if failed:
        print(f"\nSMOKE TESTS FAILED: {', '.join(failed)}")
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
