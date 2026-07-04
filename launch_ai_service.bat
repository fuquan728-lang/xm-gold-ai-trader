@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not available. Run install_python_env.bat first.
    pause
    exit /b 1
)
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python exists but cannot run. Recreate the environment with install_python_env.bat.
    pause
    exit /b 1
)
echo.
echo.
echo ================================================
echo    MT5 AI Trading System - canonical file mode
echo ================================================
echo.
python mt5_ai_service.py --mode file --log-file logs/ai_service.log
echo.
pause
