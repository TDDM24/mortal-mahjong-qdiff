@echo off
rem Start from source with the local venv (Windows).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0main_qt.py"