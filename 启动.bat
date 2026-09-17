@echo off
rem ============================================================
rem  DouK-Downloader GUI 启动脚本
rem  本文件必须以 GBK(cp936) 编码 + CRLF 换行保存：
rem    - cmd 批处理依赖 CRLF，纯 LF 会导致 goto / 代码块解析失败
rem    - 不再调用 chcp，避免运行中切换代码页导致的解析错乱
rem    - 结构上不使用 goto，且不在代码块内使用 & 转义
rem ============================================================
setlocal
cd /d "%~dp0"

set "PYEXE="

if exist ".venv\Scripts\python.exe" set "PYEXE=%CD%\.venv\Scripts\python.exe"

if not defined PYEXE for %%P in (python.exe) do if not defined PYEXE set "PYEXE=%%~$PATH:P"

if not defined PYEXE (
    echo.
    echo [错误] 未找到可用的 Python 解释器。
    echo.
    echo 请任选一种方式准备运行环境：
    echo    方式一：安装 Python 3.12 或更高版本，安装时勾选 Add Python to PATH
    echo    方式二：在本目录执行下面两条命令创建虚拟环境
    echo            python -m venv .venv
    echo            .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo   DouK-Downloader GUI
echo   解释器：%PYEXE%
echo ============================================================
echo.

"%PYEXE%" "run.py"
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" echo [完成] 程序已正常退出。
if not "%RC%"=="0" echo [错误] 程序异常退出，返回码 %RC%，请把上方报错信息反馈给开发者。

pause
endlocal
exit /b %RC%
