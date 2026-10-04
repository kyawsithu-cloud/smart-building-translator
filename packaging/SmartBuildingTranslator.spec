# PyInstaller build of the Windows app (run through packaging/build.py, which also writes version_info.txt).
#
# One folder, two programs sharing the same files:
#   SmartBuildingTranslator.exe   desktop app (no console window)
#   sbt.exe                       command line: translate, check, glossary, history, doctor, download
# Read-only files (ui/, config/, data/) go inside the folder; the translation engine and models do not — they
# are downloaded into the user's data folder (or an existing models folder is chosen in the app).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent          # noqa: F821 - provided by PyInstaller
PKG = ROOT / "packaging"
BUILD = ROOT / "build"

datas = [(str(ROOT / "ui"), "ui"), (str(ROOT / "config"), "config"), (str(ROOT / "data"), "data")]
datas += collect_data_files("sbt")           # the app's own data files (database schema)
datas += collect_data_files("rapidocr")      # OCR models (.onnx) and their configuration
datas += collect_data_files("pptx")          # python-pptx default templates
datas += collect_data_files("webview")       # pywebview's JavaScript and WebView2 interop DLLs

hidden = (collect_submodules("sbt") + ["webview.platforms.edgechromium", "webview.platforms.winforms",
                                         "clr_loader", "pythonnet"])
excludes = ["tkinter", "matplotlib", "IPython", "pytest", "ruff", "mypy", "PyInstaller", "setuptools", "pip"]


def analysis(script: str) -> Analysis:      # noqa: F821
    return Analysis([str(PKG / script)], pathex=[str(ROOT / "src")], datas=datas, hiddenimports=hidden,  # noqa: F821
                    excludes=excludes, noarchive=False)


gui, cli = analysis("gui_main.py"), analysis("cli_main.py")
common = dict(exclude_binaries=True, debug=False, strip=False, upx=False, icon=str(PKG / "app.ico"),
              version=str(BUILD / "version_info.txt"))
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], name="SmartBuildingTranslator", console=False, **common)  # noqa: F821
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], name="sbt", console=True, **common)  # noqa: F821
COLLECT(gui_exe, gui.binaries, gui.datas, cli_exe, cli.binaries, cli.datas,  # noqa: F821
        strip=False, upx=False, name="SmartBuildingTranslator")
