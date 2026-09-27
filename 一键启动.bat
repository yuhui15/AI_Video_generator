@echo off
:: 强制设置编码为 UTF-8，防止中文路径乱码
chcp 65001 >nul
cd /d "%~dp0"

echo [INFO] Checking Python environment...
if not exist ".venv" (
    echo [INFO] Creating virtual environment (.venv)...
    python -m venv .venv
)

echo [INFO] Upgrading pip...
.\.venv\Scripts\python -m pip install --upgrade pip >nul 2>&1

if exist "requirements-scraper.txt" (
    echo [INFO] Installing dependencies...
    .\.venv\Scripts\python -m pip install -r requirements-scraper.txt
)

echo [INFO] Starting Web Console...
.\.venv\Scripts\python 抓取控制台.py

pause