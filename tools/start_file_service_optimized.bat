@echo off
chcp 65001 >nul
echo ============================================================
echo MT5 AI交易服务 - 优化版 启动中...
echo ============================================================
echo.
echo 服务配置:
echo - 监听路径: c:\Users\Administrator\Desktop\XM Global MT5\MQL5\Files
echo - DeepSeek API: 已启用
echo - 性能优化: 连接池 + LRU缓存 + 性能监控
echo.
echo ============================================================
echo.
echo 按任意键启动...
pause >nul
"C:/Users/Administrator/AppData/Local/Programs/Python/Python310/python.exe "c:/Users/Administrator/Desktop/XM Global MT5/ai_file_server_optimized.py"
echo.
echo ============================================================
echo 服务已停止
pause
