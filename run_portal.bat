@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
cd app
python -m uvicorn main:app --host 127.0.0.1 --port 8050
pause
