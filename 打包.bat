@echo off
REM ============================================================
REM  DouK-Downloader GUI 打包脚本
REM  生成 dist\DouK-Downloader-GUI.exe（单文件，双击即用）
REM ============================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境 .venv\Scripts\python.exe
    echo 请先按 README 创建虚拟环境并安装依赖。
    pause
    exit /b 1
)

echo 正在打包，请稍候（约 1-3 分钟）...
".venv\Scripts\python.exe" build_exe.py

if errorlevel 1 (
    echo.
    echo [失败] 打包过程中出错，详情见上方输出。
) else (
    echo.
    echo [完成] 可执行文件：dist\DouK-Downloader-GUI.exe
)

pause
