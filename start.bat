@echo off
title AI Video Generator - Launcher
cd /d "%~dp0"

echo [INFO] Checking Python environment...
if not exist .venv python -m venv .venv

echo [INFO] Upgrading pip...
.\.venv\Scripts\python -m pip install --upgrade pip

echo [INFO] Installing dependencies...
if exist requirements-scraper.txt .\.venv\Scripts\python -m pip install -r requirements-scraper.txt

echo [INFO] Starting Web Console (console.py)...
.\.venv\Scripts\python console.py

pause