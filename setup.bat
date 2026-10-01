@echo off
rem One-time setup on a new PC. Offline if runtime\wheels exists (copied folder); otherwise downloads the
rem Python libraries from PyPI (a fresh GitHub download).
rem Requirement: Python 3.13 (64-bit) from https://www.python.org/downloads/ ("py" launcher enabled).
setlocal
cd /d "%~dp0"

py -3.13 -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo [X] Python 3.13 was not found. Install Python 3.13 ^(64-bit^) from python.org, then run setup.bat again.
  pause
  exit /b 1
)

if exist ".venv" (
  echo Removing the old Python environment ^(it only works on the PC where it was created^)...
  rmdir /s /q ".venv"
)
echo Creating the Python environment...
py -3.13 -m venv .venv || goto :fail
if exist "runtime\wheels" (
  ".venv\Scripts\python.exe" -m pip install --quiet --no-index --find-links runtime\wheels -e . || goto :fail
) else (
  ".venv\Scripts\python.exe" -m pip install --quiet -e . || goto :fail
)

set "MISSING="
if not exist "runtime\llama\llama-server.exe" set "MISSING=1"
if not exist "runtime\models\HY-MT2-7B-Q6_K.gguf" set "MISSING=1"
if defined MISSING (
  echo [!] The translation engine and model are not installed yet ^(about 7 GB^).
  echo     Copy the runtime folder from another PC, or download with:
  echo     .venv\Scripts\python.exe scripts\download_phase1.py --only llama-cuda cudart hy-mt2-7b
)
where nvidia-smi >nul 2>&1
if errorlevel 1 (
  echo [i] No NVIDIA GPU detected: translation will run on the CPU ^(slower, about 5 min per 10 slides^).
) else (
  echo [i] NVIDIA GPU detected.
)
echo.
echo Setup complete. Drag a .pptx onto translate.bat to translate it.
pause
exit /b 0

:fail
echo [X] Setup failed - see the messages above.
pause
exit /b 1
