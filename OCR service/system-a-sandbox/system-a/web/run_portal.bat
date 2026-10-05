@echo off
REM ---------------------------------------------------------------------------
REM  System A Testing Portal launcher.
REM  Starts the FastAPI portal (which shells out to process_pdf.py for every verification)
REM  and opens the browser.  No core verification code is imported or modified.
REM
REM  Usage:  run_portal.bat [port]            e.g.  run_portal.bat 8080
REM          run_portal.bat 8080 sandbox      start with MODE=sandbox in the UI default
REM ---------------------------------------------------------------------------
setlocal EnableExtensions
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8080"
set "SCRIPT_DIR=%~dp0"
set "PYMODE=%~2"
set "PY="

REM This machine has more than one Python; only some of them can import the engine's dependencies.
call :try "%SCRIPT_DIR%..\..\..\.venv\Scripts\python.exe"
call :try "%SCRIPT_DIR%..\..\.venv\Scripts\python.exe"
call :try python
call :try py

if not defined PY (
  echo.
  echo  No usable Python found.  Need one that can import:
  echo      fastapi uvicorn yaml pydantic pymupdf
  echo  Start the portal manually with your project interpreter, e.g.
  echo      python "%SCRIPT_DIR%serve.py" --port %PORT%
  exit /b 1
)

echo.
echo  System A Testing Portal   -^>  http://127.0.0.1:%PORT%
echo  python                    -^>  %PY%
echo  engine (same interpreter unless WEB_ENGINE_PYTHON is set)
echo  press Ctrl+C to stop
echo.

if /I "%PYMODE%"=="sandbox" (
  "%PY%" "%SCRIPT_DIR%serve.py" --port %PORT% --mode sandbox
) else (
  "%PY%" "%SCRIPT_DIR%serve.py" --port %PORT%
)
endlocal
exit /b 0

:try
if defined PY goto :eof
%1 -c "import fastapi, uvicorn, yaml, pydantic, pymupdf" >nul 2>&1
if not errorlevel 1 set "PY=%~1"
goto :eof
