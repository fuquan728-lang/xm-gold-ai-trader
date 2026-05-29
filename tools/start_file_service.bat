@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================================
echo MT5 AI交易服务 v3.10 - 启动中...
echo ============================================================
echo.

:: 设置Python路径
set PYTHON_PATH=C:\Users\Administrator\AppData\Local\Programs\Python\Python310\python.exe

:: 检查Python是否存在
if not exist "%PYTHON_PATH%" (
    echo ❌ 错误: 找不到Python解释器
    echo 预期路径: %PYTHON_PATH%
    echo 请安装Python 3.10或更新Python路径
    pause
    exit /b 1
)

echo ✅ Python路径: %PYTHON_PATH%

:: 检查依赖项
echo.
echo 检查Python依赖项...

:: 检查requests库
echo - 检查requests库...
"%PYTHON_PATH%" -c "import requests" >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  requests库未安装，正在安装...
    "%PYTHON_PATH%" -m pip install requests --quiet
    if errorlevel 1 (
        echo   ❌ requests库安装失败
        pause
        exit /b 1
    )
    echo   ✅ requests库安装成功
) else (
    echo   ✅ requests库已安装
)

:: 检查python-dotenv库
echo - 检查python-dotenv库...
"%PYTHON_PATH%" -c "from dotenv import load_dotenv" >nul 2>&1
if errorlevel 1 (
    echo   ⚠️  python-dotenv库未安装，正在安装...
    "%PYTHON_PATH%" -m pip install python-dotenv --quiet
    if errorlevel 1 (
        echo   ❌ python-dotenv库安装失败
        pause
        exit /b 1
    )
    echo   ✅ python-dotenv库安装成功
) else (
    echo   ✅ python-dotenv库已安装
)

:: 检查配置文件
echo.
echo 检查配置文件...
if exist ".env" (
    echo ✅ 找到.env配置文件
) else (
    echo ⚠️  未找到.env文件，使用默认配置
    echo   请复制.env.example为.env并填写配置
)

:: 显示服务配置
echo.
echo ============================================================
echo 服务配置:
echo - Python版本: 3.10.9
echo - 监听路径: c:\Users\Administrator\Desktop\XM Global MT5\MQL5\Files
echo - DeepSeek API: 按配置文件启用
echo - 精度优化: 已启用 (7指标交叉验证)
echo - 止盈功能: 已集成 (MQL5 v3.10)
echo.
echo ============================================================
echo.

:: 启动AI交易服务
echo 启动AI交易服务...
echo (按Ctrl+C停止服务)
echo.

"%PYTHON_PATH%" "c:\Users\Administrator\Desktop\XM Global MT5\ai_file_server_optimized.py"

if errorlevel 1 (
    echo.
    echo ❌ AI服务启动失败，错误码: %errorlevel%
    pause
    exit /b %errorlevel%
)

pause