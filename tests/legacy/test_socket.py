#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Socket 通信测试脚本
用于测试 Python 服务端的 Socket 通信是否正常
"""

import socket
import json
import time
import sys

def send_single_message(host, port, message, description):
    """发送单条消息并接收响应 - 使用独立连接"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((host, port))
        
        # 发送消息
        sock.sendall(message)
        
        # 接收响应
        response = sock.recv(8192)
        sock.close()
        
        print(f"� {description} 响应: {response}")
        return True, response
    except Exception as e:
        print(f"[ERR] {description} 失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def test_socket_connection(host='127.0.0.1', port=8080):
    """测试 Socket 连接 - 每个测试用独立连接"""
    print("=" * 60)
    print("测试 Socket 连接")
    print("=" * 60)
    
    all_success = True
    
    # 测试 1: 发送 TEST 消息 - 独立连接
    print("\n" + "-" * 60)
    print("测试 1: 发送 TEST 消息")
    print("-" * 60)
    
    success1, response1 = send_single_message(host, port, b"TEST\n", "TEST 消息")
    if success1 and response1:
        print(f"📥 解码后: {response1.decode('utf-8', errors='ignore')}")
    else:
        all_success = False
    
    # 等待一下
    time.sleep(0.5)
    
    # 测试 2: 发送 JSON 数据 - 独立连接
    print("\n" + "-" * 60)
    print("测试 2: 发送 JSON 数据")
    print("-" * 60)
    
    test_data = {
        "symbol": "EURUSD",
        "bid": 1.09876,
        "ask": 1.09886,
        "time": int(time.time()),
        "history": [],
        "indicators": {
            "rsi": 50.5,
            "macd_main": 0.00123,
            "macd_signal": 0.00110,
            "ema50": 1.09800
        }
    }
    
    json_str = json.dumps(test_data, ensure_ascii=False) + "\n"
    json_bytes = json_str.encode('utf-8')
    
    print(f"📤 发送 JSON 数据 ({len(json_bytes)} 字节)...")
    print(f"📤 数据内容: {json_str[:100]}...")
    
    success2, response2 = send_single_message(host, port, json_bytes, "JSON 数据")
    if success2 and response2:
        print(f"📥 解码后: {response2.decode('utf-8', errors='ignore')}")
    else:
        all_success = False
    
    # 总结
    print("\n" + "=" * 60)
    if all_success:
        print("[OK] 所有测试通过！")
    else:
        print("[WARN]  部分测试失败！")
    print("=" * 60)
    
    return all_success

if __name__ == "__main__":
    host = '127.0.0.1'
    port = 8080
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    
    success = test_socket_connection(host, port)
    sys.exit(0 if success else 1)
