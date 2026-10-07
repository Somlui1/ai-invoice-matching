@echo off
rem Starts the AIVA System A test application (Windows).  Edit .env first (copy .env.example).
cd /d "%~dp0"
rem The interpreter is used by FULL PATH on purpose.  "call .venv\Scripts\activate.bat" is not enough: it puts
rem %VIRTUAL_ENV%\Scripts on PATH, and that value is fixed when the venv is created - once this folder is moved
rem it points at the old place, so "python" silently falls back to whatever interpreter is first on PATH (i.e.
rem another project's venv).  See agent/errors-and-solutions.md ERR-20261007-001.
if not exist .venv\Scripts\python.exe py -3 -m venv .venv
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo cannot find .venv\Scripts\python.exe - create it with:  py -3 -m venv .venv
  pause
  exit /b 2
)
"%PY%" -m pip install -q -r requirements.txt
"%PY%" -m webapp check && "%PY%" -m webapp serve
pause
