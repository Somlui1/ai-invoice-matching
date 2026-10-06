@echo off
rem Starts the AIVA System A test application (Windows).  Edit .env first (copy .env.example).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
python -m webapp check && python -m webapp serve
pause
