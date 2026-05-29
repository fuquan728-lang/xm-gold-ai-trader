@echo off
setlocal enabledelayedexpansion
title MT5 AI Trading - Python Env Setup

echo.
echo ================================================================
echo     MT5 AI Trading System V3.1 - Environment Setup
echo ================================================================
echo.

:: ============================================================
::  STEP 0 - Admin check (inform only, don't auto-elevate)
:: ============================================================
echo [0/6] Checking administrator privileges...
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo ================================================================
    echo   WARNING: This script requires ADMINISTRATOR privileges!
    echo ================================================================
    echo.
    echo   Please close this window and:
    echo   >> Right-click install_python_env.bat >> "Run as administrator"
    echo.
    pause
    exit /b 1
)
echo [ OK ] Administrator privileges confirmed
echo.

:: ============================================================
::  STEP 1 - Check / Install Python
:: ============================================================
echo [1/6] Checking Python environment...

set PYTHON_VERSION=3.12
set PYTHON_FULL_VER=3.12.8
set PYTHON_INSTALLER=python-%PYTHON_FULL_VER%-amd64.exe
set PYTHON_DOWNLOAD_URL=https://www.python.org/ftp/python/%PYTHON_FULL_VER%/%PYTHON_INSTALLER%
set PYTHON_INSTALL_DIR=C:\Python312
set PYTHON_EXE=%PYTHON_INSTALL_DIR%\python.exe

where python >nul 2>&1
if errorlevel 1 goto install_python

python --version 2>&1 | findstr /i "3.12 3.13" >nul
if not errorlevel 1 (
    echo [ OK ] System Python already meets requirement (3.12+), skipping install.
    for /f "tokens=*" %%i in ('python -c "import sys; print(sys.executable)"') do set PYTHON_EXE=%%i
    goto check_pip
)

:install_python
if exist "%PYTHON_EXE%" (
    echo [ OK ] Python already installed at %PYTHON_INSTALL_DIR%
    goto check_pip
)

echo.
echo [INFO] Downloading Python %PYTHON_FULL_VER% ...
echo        URL: %PYTHON_DOWNLOAD_URL%

set DOWNLOAD_PATH=%TEMP%\%PYTHON_INSTALLER%

powershell -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%PYTHON_DOWNLOAD_URL%' -OutFile '%DOWNLOAD_PATH%'"
if errorlevel 1 (
    echo [ERROR] Python download failed! Check your internet connection.
    pause
    exit /b 1
)
echo [ OK ] Downloaded

echo.
echo [INFO] Installing Python %PYTHON_FULL_VER% to %PYTHON_INSTALL_DIR% ...
echo        This may take 1-2 minutes, please wait...

"%DOWNLOAD_PATH%" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1 TargetDir=%PYTHON_INSTALL_DIR%
if errorlevel 1 (
    echo [ERROR] Python installation failed!
    pause
    exit /b 1
)

set PATH=%PYTHON_INSTALL_DIR%;%PYTHON_INSTALL_DIR%\Scripts;%PATH%

:check_pip
if not exist "%PYTHON_EXE%" (
    set PYTHON_EXE=python
)
echo [ OK ] Python: %PYTHON_EXE%
"%PYTHON_EXE%" --version
echo.

:: ============================================================
::  STEP 2 - Upgrade pip
:: ============================================================
echo [2/6] Upgrading pip...
"%PYTHON_EXE%" -m pip install --upgrade pip --quiet
echo [ OK ] Done
echo.

:: ============================================================
::  STEP 3 - Create virtual environment
:: ============================================================
echo [3/6] Creating virtual environment...

set VENV_DIR=%~dp0venv

if exist "%VENV_DIR%" (
    echo [INFO] Virtual environment already exists.
    echo        Press Y to recreate, N to keep existing.
    choice /c yn /n /m "[Y/N]: "
    if errorlevel 2 goto activate_venv
    if errorlevel 1 (
        echo [INFO] Removing old virtual environment...
        rmdir /s /q "%VENV_DIR%"
    )
)

echo [INFO] Creating venv at: %VENV_DIR%
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [ERROR] Virtual environment creation failed!
    pause
    exit /b 1
)

:activate_venv
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe
set VENV_PIP=%VENV_DIR%\Scripts\pip.exe
echo [ OK ] Virtual environment ready
echo.

:: ============================================================
::  STEP 4 - Install project dependencies
:: ============================================================
echo [4/6] Installing project dependencies...

"%VENV_PYTHON%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --quiet

set REQ_FILE=%~dp0requirements.txt
if not exist "%REQ_FILE%" (
    echo [WARN] requirements.txt not found, installing default set...
    "%VENV_PIP%" install requests python-dotenv websockets Flask pandas numpy sqlalchemy scikit-learn joblib matplotlib psutil aiohttp -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    goto verify_install
)

echo [INFO] Installing from: %REQ_FILE%
echo        Mirror: https://pypi.tuna.tsinghua.edu.cn/simple
"%VENV_PIP%" install -r "%REQ_FILE%" -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

echo.
echo [INFO] Installing additional packages: psutil, aiohttp
"%VENV_PIP%" install psutil aiohttp -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

:verify_install
echo.
echo [INFO] Verification:

set ALL_OK=1
for %%p in (requests dotenv websockets flask pandas numpy sqlalchemy sklearn joblib matplotlib psutil aiohttp) do (
    "%VENV_PYTHON%" -c "import %%p" >nul 2>&1
    if not errorlevel 1 (
        echo   [ OK ] %%p
    ) else (
        echo   [FAIL] %%p
        set ALL_OK=0
    )
)

if %ALL_OK% equ 1 (
    echo [ OK ] All packages verified!
) else (
    echo [WARN] Some packages failed - see [FAIL] items above
)
echo.

:: ============================================================
::  STEP 5 - Environment configuration
:: ============================================================
echo [5/6] Configuring environment...

set ENV_FILE=%~dp0.env
if not exist "%ENV_FILE%" (
    echo [INFO] Creating .env template...
    (
        echo # MT5 AI Trading System - Environment Config
        echo # Edit this file with your actual settings
        echo.
        echo DEEPSEEK_API_KEY=your-deepseek-api-key-here
        echo DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
        echo USE_DEEPSEEK=false
        echo.
        echo MT5_EA_HOST=127.0.0.1
        echo SOCKET_HOST=127.0.0.1
        echo SOCKET_PORT=8080
        echo WEBSOCKET_PORT=8081
        echo HTTP_PORT=8000
        echo.
        echo MAX_RISK_PER_TRADE=0.02
        echo MIN_RISK_REWARD_RATIO=1.5
        echo MAX_POSITIONS=3
        echo.
        echo LOG_LEVEL=INFO
        echo LOG_DIR=%~dp0logs
    ) > "%ENV_FILE%"
    echo [ OK ] .env created - EDIT IT with your API key!
)

:: Create launcher
set LAUNCHER=%~dp0launch_ai_service.bat
(
    echo @echo off
    echo cd /d "%~dp0"
    echo call "%VENV_DIR%\Scripts\activate.bat"
    echo echo.
    echo echo ================================================
    echo echo    MT5 AI Trading System V3.1
    echo echo ================================================
    echo echo.
    echo echo Select launch mode:
    echo echo [1] File mode ^(recommended - matches default EA^)
    echo echo [2] Socket mode
    echo echo [3] Async-optimized ^(File^)
    echo echo [4] Integrated mode
    echo echo [5] Custom args
    echo echo.
    echo set /p MODE="Enter mode ^(1-5^): "
    echo.
    echo if "%%MODE%%"=="1" ^(python mt5_ai_service.py --mode file^)
    echo if "%%MODE%%"=="2" ^(python mt5_ai_service.py --mode socket^)
    echo if "%%MODE%%"=="3" ^(python mt5_ai_service_optimized.py --mode file^)
    echo if "%%MODE%%"=="4" ^(python ai_service_integrated.py^)
    echo if "%%MODE%%"=="5" ^(
    echo     set /p ARGS="Enter startup args: "
    echo     python mt5_ai_service.py %%ARGS%%
    echo ^)
    echo if not defined MODE ^(python mt5_ai_service.py --mode file^)
    echo.
    echo pause
) > "%LAUNCHER%"
echo [ OK ] Launcher created: launch_ai_service.bat
echo.

:: ============================================================
::  STEP 6 - Done
:: ============================================================
echo ================================================================
echo                  INSTALLATION COMPLETE!
echo ================================================================
echo.
echo    Summary:
echo    -------------------------------------------------------
echo    Python:     v%PYTHON_VERSION% (%PYTHON_FULL_VER%)
echo    Install:    %PYTHON_INSTALL_DIR%
echo    VENV:       %VENV_DIR%
echo    Project:    %~dp0
echo    -------------------------------------------------------
echo.
echo    Quick start:
echo    1. Run: launch_ai_service.bat
echo    2. Or in CMD:
echo       cd /d "%~dp0"
echo       "%VENV_DIR%\Scripts\activate.bat"
echo       python mt5_ai_service.py --mode file
echo.
echo    IMPORTANT:
echo    - Edit .env and set your DEEPSEEK_API_KEY first!
echo    - Ensure MT5 terminal is running with EA loaded
echo    - Socket mode uses port 8080 when enabled
echo.
pause
exit /b 0
