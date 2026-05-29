#!/usr/bin/env python3
"""
检查核心配置模块状态
"""
import sys
sys.path.insert(0, '.')

try:
    from core.config import *
    print('[PASS] 配置导入成功')
    print(f'MQL5_DATA_PORT: {MQL5_DATA_PORT if "MQL5_DATA_PORT" in globals() else "未定义"}')
    print(f'SOCKET_PORT: {SOCKET_PORT if "SOCKET_PORT" in globals() else "未定义"}')
    print(f'WEBSOCKET_PORT: {WEBSOCKET_PORT if "WEBSOCKET_PORT" in globals() else "未定义"}')
    print(f'HTTP_PORT: {HTTP_PORT if "HTTP_PORT" in globals() else "未定义"}')
except Exception as e:
    print(f'[FAIL] 导入失败: {e}')
    import traceback
    traceback.print_exc()