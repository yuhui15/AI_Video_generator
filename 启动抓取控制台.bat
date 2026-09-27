@echo off
title AI Video Generator Launcher
cd /d "%~dp0"

echo ========================================================
echo         AI Video Generator - 启动器
echo ========================================================
echo.

:: 检查系统中是否存在 python
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [错误] 未检测到 Python！请确保已安装 Python 并勾选了 Add to PATH。
        goto error_exit
    )
)

:: 检查并创建虚拟环境
if not exist ".venv" (
    echo [信息] 正在创建 Python 虚拟环境 (.venv)...
    py -3.11 -m venv .venv || python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败！
        goto error_exit
    )
    echo [成功] 虚拟环境创建完成。
    echo.
)

:: 安装依赖
echo [信息] 正在检查并安装依赖包...
.\.venv\Scripts\python.exe -m pip install --upgrade pip
if exist "requirements-scraper.txt" (
    .\.venv\Scripts\python.exe -m pip install -r requirements-scraper.txt
    if errorlevel 1 (
        echo [警告] 部分依赖安装失败，请检查网络连接。
    )
)
echo.

:: 启动网页控制台
echo ========================================================
echo [信息] 正在启动网页控制台...
echo [提示] 浏览器访问地址: http://127.0.0.1:8765
echo ========================================================
echo.

.\.venv\Scripts\python.exe .\抓取控制台.py

if errorlevel 1 (
    echo.
    echo [错误] 抓取控制台异常退出。
    goto error_exit
)

goto end

:error_exit
echo.
echo ========================================================
echo 启动失败！请把上面红字或报错信息截图发给我排查。
echo ========================================================

:end
pause