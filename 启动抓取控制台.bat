@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "抓取控制台.py"
) else (
    py -3 "抓取控制台.py"
)

pause
