@echo off
setlocal
title Codex Armorum

cd /d "%~dp0"
set "CODEX_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%CODEX_PYTHON%" (
  echo.
  echo Codex Armorum could not find its Python environment:
  echo   %CODEX_PYTHON%
  echo.
  echo Create it with: python -m venv .venv
  echo Then install dependencies with: .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

"%CODEX_PYTHON%" "%~dp0app.py" %*
set "CODEX_EXIT=%ERRORLEVEL%"

if not "%CODEX_EXIT%"=="0" (
  echo.
  echo Codex Armorum stopped with exit code %CODEX_EXIT%.
  pause
)

exit /b %CODEX_EXIT%
