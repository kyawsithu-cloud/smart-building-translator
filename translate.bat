@echo off
rem Smart Building Translator (offline).
rem   Drag a .pptx or .pdf onto this file, or run:  translate.bat "C:\path\file.pptx" [src] [tgt]
rem   src/tgt default to auto: English documents -> Japanese, Japanese documents -> English.
setlocal
set "ROOT=%~dp0"
if "%~1"=="" (
  echo Drag a .pptx or .pdf file onto translate.bat, or run: translate.bat "C:\path\file.pptx" [en^|ja] [ja^|en]
  pause
  exit /b 1
)
set "SRC=%~2"
set "TGT=%~3"
if "%SRC%"=="" set "SRC=auto"
if "%TGT%"=="" set "TGT=auto"
"%ROOT%.venv\Scripts\python.exe" -m sbt translate "%~1" --src %SRC% --tgt %TGT%
echo.
pause
