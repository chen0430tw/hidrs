@echo off
chcp 65001 >nul
title FAIRY-DESK + Claude Code

echo.
echo   ╔═══════════════════════════════════════════╗
echo   ║      🧿 FAIRY-DESK + Claude Code          ║
echo   ║         启动脚本 v1.0.0                   ║
echo   ╚═══════════════════════════════════════════╝
echo.

:: 检查 Node.js
where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Node.js 未安装
    echo 请先安装 Node.js: https://nodejs.org/
    pause
    exit /b 1
)

:: 检查 Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Python 未安装
    pause
    exit /b 1
)

:: 检查 claude CLI
where claude >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ⚠️  Claude Code CLI 未安装
    echo 安装命令: irm https://claude.ai/install.ps1 ^| iex
    echo.
    set /p SKIP_CLAUDE="是否继续启动 FAIRY-DESK（不含 Claude Code）? [y/N] "
    if /i not "%SKIP_CLAUDE%"=="y" exit /b 1
    set SKIP_CLAUDE=1
)

:: 获取脚本目录
cd /d "%~dp0"

:: 启动 claude-code-web
if not defined SKIP_CLAUDE (
    echo ▶ 启动 claude-code-web...
    start "Claude Code Web" /min cmd /c "npx claude-code-web --port 3000"
    echo ✓ claude-code-web 已启动
    echo   地址: http://localhost:3000
    echo.
    timeout /t 3 /nobreak >nul
)

:: 安装 Python 依赖
if not exist "venv" (
    echo ▶ 创建 Python 虚拟环境...
    python -m venv venv
)

echo ▶ 安装 Python 依赖...
call venv\Scripts\activate.bat
pip install -q -r requirements.txt

:: 启动 FAIRY-DESK
echo ▶ 启动 FAIRY-DESK...
echo.
echo ═══════════════════════════════════════════
echo ✓ 服务已启动
echo ═══════════════════════════════════════════
echo.
echo   FAIRY-DESK:       http://localhost:8080
echo   三联屏预览:       http://localhost:8080/preview
if not defined SKIP_CLAUDE (
    echo   Claude Code Web:  http://localhost:3000
)
echo.
echo 按 Ctrl+C 停止 FAIRY-DESK
echo.

:: 启动 FAIRY-DESK（前台）
python app.py

:: 停止 claude-code-web
if not defined SKIP_CLAUDE (
    taskkill /FI "WINDOWTITLE eq Claude Code Web" /F >nul 2>nul
)

echo.
echo ✓ 已停止
pause
