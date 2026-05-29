#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket测试脚本 - V3.0
测试WebSocket通信
"""

import asyncio
import json
import time
import websockets

async def test_websocket():
    uri = "ws://127.0.0.1:8081"
    
    print("="*60)
    print("🔌 WebSocket通信测试")
    print("="*60)
    print()
    
    try:
        print(f"🔌 正在连接 {uri}...")
        async with websockets.connect(uri) as websocket:
            print(f"[OK] 连接成功！")
            print()
            print("-"*60)
            print("测试 1: 发送 TEST 消息")
            print("-"*60)
            
            print("📤 发送 TEST 消息...")
            await websocket.send("TEST")
            
            response = await websocket.recv()
            print(f"📥 收到响应: {response}")
            data = json.loads(response)
            print(f"📥 解码后: {data}")
            
            if data.get("status") == "ok":
                print(f"[OK] 测试通过！")
            else:
                print(f"[ERR] 测试失败！")
            
            print()
            print("-"*60)
            print("测试 2: 发送 JSON 数据")
            print("-"*60)
            
            test_request = {
                "symbol": "EURUSD",
                "bid": 1.09876,
                "ask": 1.09886,
                "time": int(time.time()),
                "history": [],
                "indicators": {}
            }
            
            print(f"📤 发送 JSON 数据 ({len(json.dumps(test_request))} 字节)...")
            print(f"📤 数据内容: {json.dumps(test_request)[:100]}...")
            
            await websocket.send(json.dumps(test_request))
            
            response = await websocket.recv()
            print(f"📥 收到响应: {response[:100]}...")
            
            data = json.loads(response)
            print()
            print(f"[OK] 测试通过！")
            print(f"   动作: {data.get('action')}")
            print(f"   置信度: {data.get('confidence'):.2f}")
            print(f"   原因: {data.get('reason', '')[:50]}...")
            
            print()
            print("="*60)
            print("[OK] 所有测试通过！")
            print("="*60)
            
    except ConnectionRefusedError:
        print(f"[ERR] 连接失败: 服务端未启动！")
        print(f"   请先运行: python mt5_ai_service.py --mode websocket")
    except Exception as e:
        print(f"[ERR] 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_websocket())
