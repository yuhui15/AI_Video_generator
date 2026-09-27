@echo off
title AI Video Generator - Launcher (Auto CLIP Setup)
cd /d "%~dp0"

echo [INFO] Checking Python environment...
if not exist .venv python -m venv .venv

echo [INFO] Upgrading pip (using Tsinghua mirror)...
.\.venv\Scripts\python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [INFO] Installing dependencies (using Tsinghua mirror)...
if exist requirements-scraper.txt .\.venv\Scripts\python -m pip install -r requirements-scraper.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [INFO] Ensuring ModelScope is available for domestic asset download...
.\.venv\Scripts\python -m pip install modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet

echo [INFO] Checking and auto-downloading CLIP model (via ModelScope domestic mirror)...
.\.venv\Scripts\python -c "import os; from modelscope import snapshot_download; model_dir = os.path.join(r'%~dp0', 'models', 'clip-vit-large-patch14'); os.makedirs(model_dir, exist_ok=True); print('[INFO] Local model directory:', model_dir); snapshot_download('AI-ModelScope/clip-vit-large-patch14', local_dir=model_dir)"

echo [INFO] Starting Web Console (console.py)...
.\.venv\Scripts\python console.py

pause