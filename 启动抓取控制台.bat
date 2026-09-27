@echo off
chcp 65001 >nul

echo ========================================================
echo         AI Video Generator - Environment Setup
echo ========================================================
echo.

if not exist ".venv" (
    echo [INFO] Creating Python virtual environment (.venv)...
    py -3.11 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment! Please ensure Python 3.10+ is installed.
        goto error_exit
    )
    echo [SUCCESS] Virtual environment created.
    echo.
)

echo [INFO] Installing and upgrading dependencies...
.\.venv\Scripts\python.exe -m pip install --upgrade pip >nul 2>&1

if exist "requirements-scraper.txt" (
    .\.venv\Scripts\python.exe -m pip install -r requirements-scraper.txt
    if errorlevel 1 (
        echo [WARNING] Some dependencies might have failed to install. Please check network.
    )
) else (
    echo [NOTICE] requirements-scraper.txt not found, skipping.
)
echo.

echo ========================================================
echo [INFO] Starting web console...
echo [INFO] Open in your browser: http://127.0.0.1:8765
echo [INFO] Keep this window open. Press Ctrl+C to stop.
echo ========================================================
echo.

.\.venv\Scripts\python.exe .\抓取控制台.py

goto end

:error_exit
echo.
echo [ERROR] Startup failed. Please check environment.
:end
pause