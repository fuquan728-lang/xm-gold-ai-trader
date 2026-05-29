@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo 启动Socket服务器
echo ===========================================

cd /d "%~dp0"

python test_simple_server.py

pause