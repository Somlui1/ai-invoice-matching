@echo off
chcp 65001 > nul
cd /d "%~dp0\.."

echo ===============================================================================
echo   AIVA System A — Batch Invoice Verification Runner
echo ===============================================================================
echo.

python scripts/test_paperless_invoices.py %*
pause
