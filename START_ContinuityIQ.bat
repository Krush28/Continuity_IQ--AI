@echo off
title ContinuityIQ server
cd /d "%~dp0backend"
if not exist .venv (
  echo [1/3] Creating Python environment...
  py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
echo [2/3] Installing packages (first run takes a minute)...
python -m pip install -q --disable-pip-version-check -r requirements.txt
if not exist continuityiq.db (
  echo Loading demo project...
  python ..\scripts\seed_demo.py
)
echo [3/3] ContinuityIQ is running at http://localhost:8000  -  keep this window open, close it to stop.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
