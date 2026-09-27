@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Checking Python environment...
if not exist ".venv" (
python -m venv .venv
)

echo [INFO] Upgrading pip...
.\.venv\Scripts\python -m pip install --upgrade pip

if exist "requirements-scraper.txt" (
echo [INFO] Installing dependencies...
.\.venv\Scripts\python -m pip install -r requirements-scraper.txt
)

echo [INFO] Starting Web Console...
.\.venv\Scripts\python 抓取控制台.py

pause