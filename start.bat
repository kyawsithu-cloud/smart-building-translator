@echo off
rem Opens the Smart Building Translator desktop app (no console window).
setlocal
set "ROOT=%~dp0"
if not exist "%ROOT%.venv\Scripts\pythonw.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
start "" "%ROOT%.venv\Scripts\pythonw.exe" -m sbt ui
