@echo off
chcp 65001 >nul
echo [INFO] 正在关闭图片抓取与发布控制台服务器...

:: 查找并强行杀死占用 8765 端口的 Python 进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8765') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo [SUCCESS] 网页服务器已成功关闭！
pause