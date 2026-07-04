@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo 启动MT5 AI交易系统 - 企业级增强版 V3.0
echo ============================================================
echo.

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

python mt5_ai_service.py --mode file

pause
