@echo off
title AI Video Generator - Launcher (China Mirror)
cd /d "%~dp0"

set HF_ENDPOINT=https://hf-mirror.com

echo [INFO] Checking Python environment...
if not exist .venv python -m venv .venv

echo [INFO] Upgrading pip (using Tsinghua mirror)...
.\.venv\Scripts\python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [INFO] Installing dependencies (using Tsinghua mirror)...
if exist requirements-scraper.txt .\.venv\Scripts\python -m pip install -r requirements-scraper.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [INFO] Starting Web Console (console.py)...
.\.venv\Scripts\python console.py

pause