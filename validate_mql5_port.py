#!/usr/bin/env python3
"""
验证MQL5_DATA_PORT配置
"""
import sys
sys.path.insert(0, '.')

try:
    from core.config import *
    print('[PASS] 配置导入成功')
    
    # 检查MQL5_DATA_PORT
    if 'MQL5_DATA_PORT' in globals():
        print(f'MQL5_DATA_PORT: {MQL5_DATA_PORT}')
    else:
        print('MQL5_DATA_PORT: 未定义')
        
    # 检查所有关键端口
    ports = {
        'SOCKET_PORT': SOCKET_PORT,
        'WEBSOCKET_PORT': WEBSOCKET_PORT,
        'HTTP_PORT': HTTP_PORT,
        'MQL5_DATA_PORT': MQL5_DATA_PORT if 'MQL5_DATA_PORT' in globals() else None
    }
    
    print('\n所有端口配置:')
    for name, port in ports.items():
        if port is None:
            print(f'  {name}: 未定义')
        else:
            print(f'  {name}: {port}')
    
    # 检查端口冲突
    port_values = [p for p in ports.values() if p is not None]
    if len(port_values) != len(set(port_values)):
        print('\n[WARNING] 检测到端口冲突！')
    else:
        print('\n[OK] 所有端口无冲突')
        
except Exception as e:
    print(f'[ERROR] 导入配置失败: {e}')
    import traceback
    traceback.print_exc()