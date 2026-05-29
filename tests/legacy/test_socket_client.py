#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Socket客户端测试脚本 - 模拟EA请求
用于调试Socket服务器
"""

import socket
import json
import time

def test_socket_request():
    """发送测试Socket请求"""
    host = '127.0.0.1'
    port = 8080
    
    # 模拟EA请求数据
    test_request = {
        "symbol": "BTCUSD",
        "bid": 65200.50,
        "ask": 65201.50,
        "time": time.time(),
        "history": [
            {"open": 65100, "high": 65300, "low": 65000, "close": 65200, "volume": 1000}
        ],
        "indicators": {
            "rsi": 50.0,
            "macd": {"histogram": 0.0, "signal": 0.0, "macd": 0.0},
            "ema": {"fast": 65150, "slow": 65100}
        }
    }
    
    print("="*60)
    print("🧪 Socket客户端测试")
    print("="*60)
    print()
    
    print(f"📤 连接到 {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(60.0)  # 60秒超时
        sock.connect((host, port))
        print("[OK] 连接成功")
        print()
        
        request_json = json.dumps(test_request, ensure_ascii=False)
        print(f"📤 发送请求: {request_json[:100]}...")
        sock.sendall(request_json.encode('utf-8'))
        print("[OK] 请求已发送")
        print()
        
        print("📥 等待响应...")
        response_data = sock.recv(8192).decode('utf-8')
        print("[OK] 收到响应")
        print()
        
        print("[DATA] 响应内容:")
        print("-"*60)
        print(response_data)
        print("-"*60)
        print()
        
        try:
            response_json = json.loads(response_data.strip())
            print("[OK] 响应是有效的JSON!")
            print(f"   Action: {response_json.get('action')}")
            print(f"   Confidence: {response_json.get('confidence')}")
            print(f"   Use DeepSeek: {response_json.get('use_deepseek')}")
        except json.JSONDecodeError as e:
            print(f"[ERR] JSON解析失败: {e}")
            print(f"   原始响应: '{response_data}'")
        
        sock.close()
        print()
        print("[OK] 测试完成")
        
    except Exception as e:
        print(f"[ERR] 错误: {e}")

if __name__ == "__main__":
    test_socket_request()
