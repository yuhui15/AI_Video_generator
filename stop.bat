@echo off
title AI Video Generator - Stopper
chcp 65001 >nul
echo [INFO] Stopping Web Console server (Port 8765)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8765') do taskkill /f /pid %%a >nul 2>&1
echo [SUCCESS] Web server has been successfully stopped!
pause