@echo off
rem Smart Building Translator (Phase 1, offline).
rem   Drag a .pptx onto this file, or run:  translate.bat "C:\path\deck.pptx" [src] [tgt]
rem   src/tgt default to auto: English decks -> Japanese, Japanese decks -> English.
setlocal
set "ROOT=%~dp0"
if "%~1"=="" (
  echo Drag a .pptx file onto translate.bat, or run: translate.bat "C:\path\deck.pptx" [en^|ja] [ja^|en]
  pause
  exit /b 1
)
set "SRC=%~2"
set "TGT=%~3"
if "%SRC%"=="" set "SRC=auto"
if "%TGT%"=="" set "TGT=auto"
"%ROOT%.venv\Scripts\python.exe" -m sbt.poc translate "%~1" --src %SRC% --tgt %TGT%
echo.
pause
