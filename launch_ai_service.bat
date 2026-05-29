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
echo ================================================
echo    MT5 AI Trading System V3.1
echo ================================================
echo.
echo Select launch mode:
echo [1] File mode (recommended - matches EA)
echo [2] Socket mode
echo [3] Async-optimized
echo [4] Integrated mode
echo [5] Custom args
echo.
set /p MODE="Enter mode (1-5): "
echo.
if "%MODE%"=="1" (python mt5_ai_service.py --mode file)
if "%MODE%"=="2" (python mt5_ai_service.py --mode socket)
if "%MODE%"=="3" (python mt5_ai_service_optimized.py --mode file)
if "%MODE%"=="4" (python ai_service_integrated.py)
if "%MODE%"=="5" (
    set /p ARGS="Enter startup args: "
    python mt5_ai_service.py %ARGS%
)
if not defined MODE (python mt5_ai_service.py --mode file)
echo.
pause
