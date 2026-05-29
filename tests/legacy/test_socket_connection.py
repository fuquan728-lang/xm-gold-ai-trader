#!/usr/bin/env python3
"""
测试Socket连接和AI服务
"""

import socket
import json
import time
import sys

def test_socket_connection():
    """测试Socket连接"""
    print("测试Socket连接...")
    
    # 尝试连接
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('127.0.0.1', 8080))
        
        if result == 0:
            print("[PASS] Socket端口8080连接成功")
            
            # 发送测试数据
            test_request = {
                "symbol": "GOLD",
                "bid": 1912.34,
                "ask": 1912.56,
                "time": int(time.time()),
                "indicators": {
                    "rsi": 45.2,
                    "macd": -1.5,
                    "ema20": 1910.5
                }
            }
            
            request_str = json.dumps(test_request) + "\n"
            sock.sendall(request_str.encode('utf-8'))
            
            # 接收响应
            response = b""
            sock.settimeout(2)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
                    if b'\n' in response:
                        break
            except socket.timeout:
                pass
            
            if response:
                try:
                    response_str = response.decode('utf-8').strip()
                    print(f"[PASS] 收到响应: {response_str[:200]}...")
                    
                    # 解析响应
                    resp_data = json.loads(response_str)
                    print(f"[PASS] 解析成功:")
                    print(f"   动作: {resp_data.get('action')}")
                    print(f"   置信度: {resp_data.get('confidence')}")
                    print(f"   符号: {resp_data.get('symbol')}")
                    
                except Exception as e:
                    print(f"[FAIL] 解析响应失败: {e}")
                    print(f"原始响应: {response[:200]}...")
            else:
                print("[WARN] 未收到响应")
            
            sock.close()
        else:
            print(f"[FAIL] Socket端口8080连接失败，错误码: {result}")
            
    except Exception as e:
        print(f"[FAIL] 连接测试异常: {e}")
    
    print("\n测试WebSocket连接...")
    try:
        import asyncio
        import websockets
        
        async def test_websocket():
            try:
                async with websockets.connect('ws://127.0.0.1:8081', timeout=3) as ws:
                    print("[PASS] WebSocket连接成功")
                    
                    # 发送测试消息
                    test_msg = {
                        "symbol": "EURUSD",
                        "bid": 1.0865,
                        "ask": 1.0867
                    }
                    
                    await ws.send(json.dumps(test_msg))
                    
                    # 接收响应
                    try:
                        response = await asyncio.wait_for(ws.recv(), timeout=2)
                        print(f"[PASS] 收到WebSocket响应: {response[:200]}...")
                    except asyncio.TimeoutError:
                        print("[WARN] WebSocket响应超时")
                        
            except Exception as e:
                print(f"[FAIL] WebSocket连接失败: {e}")
        
        asyncio.run(test_websocket())
        
    except ImportError:
        print("[WARN] 缺少websockets库，跳过WebSocket测试")
    except Exception as e:
        print(f"[FAIL] WebSocket测试异常: {e}")
    
    print("\n测试HTTP Dashboard...")
    try:
        import urllib.request
        import urllib.error
        
        try:
            resp = urllib.request.urlopen('http://127.0.0.1:8000/api/stats', timeout=5)
            data = resp.read().decode('utf-8')
            print(f"[PASS] Dashboard API响应: {data[:200]}...")
        except Exception as e:
            print(f"[FAIL] Dashboard API请求失败: {e}")
            
    except Exception as e:
        print(f"[FAIL] Dashboard测试异常: {e}")

def check_mql5_connection():
    """检查MQL5数据连接"""
    print("\n检查MQL5数据连接...")
    
    try:
        # 尝试导入MQL5数据管理器
        sys.path.insert(0, '.')
        from core.mql5_data import MQL5DataManager
        
        manager = MQL5DataManager()
        
        # 获取数据
        account_info = manager.account_info
        positions = manager.positions
        
        print(f"账户信息:")
        print(f"  余额: {account_info.balance}")
        print(f"  净值: {account_info.equity}")
        print(f"  已用保证金: {account_info.margin}")
        print(f"  可用保证金: {account_info.margin_free}")
        print(f"  保证金水平: {account_info.margin_level}")
        print(f"  账户号: {account_info.account}")
        
        print(f"持仓数量: {len(positions)}")
        for pos in positions:
            print(f"  - {pos.symbol}: {pos.type} {pos.volume}手 @ {pos.open_price}, 盈亏: {pos.profit}")
        
        # 检查保证金计算
        if account_info.margin > 0:
            margin_level_calc = account_info.equity / account_info.margin * 100 if account_info.margin > 0 else 0
            print(f"计算保证金水平: {margin_level_calc:.2f}%")
        else:
            print("[WARN] 已用保证金为0，可能未连接到MT5")
            
    except Exception as e:
        print(f"[FAIL] MQL5数据管理器检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("MT5 AI交易系统连接测试")
    print("=" * 60)
    
    test_socket_connection()
    check_mql5_connection()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)