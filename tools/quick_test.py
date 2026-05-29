#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试优化版服务
"""

import os
import time
import json
from datetime import datetime
from pathlib import Path

TEST_DIR = Path(r"c:\Users\Administrator\Desktop\XM Global MT5\MQL5\Files")

def test_optimized_service():
    print("="*60)
    print("快速测试优化版服务")
    print("="*60)
    print()
    
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    
    request_file = TEST_DIR / "ai_request.json"
    response_file = TEST_DIR / "ai_response.json"
    
    test_data = {
        "symbol": "XAUUSD",
        "bid": 2000.00,
        "ask": 2000.50,
        "time": int(time.time()),
        "history": [
            {
                "time": int(time.time()) - 3600,
                "open": 1990.00,
                "high": 2005.00,
                "low": 1985.00,
                "close": 2000.00,
                "volume": 1000
            }
        ],
        "indicators": {
            "rsi": 55.5,
            "macd_main": 0.0001,
            "macd_signal": -0.0002,
            "ema50": 1995.00
        }
    }
    
    print(f"测试数据: {test_data['symbol']} @ {test_data['bid']}")
    print(f"写入请求文件...")
    
    try:
        with open(request_file, 'w') as f:
            json.dump(test_data, f)
        
        print(f"等待响应 (最多30秒)...")
        
        start_time = time.time()
        wait_count = 0
        
        while time.time() - start_time < 30:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r') as f:
                        response = json.load(f)
                    
                    elapsed = time.time() - start_time
                    print()
                    print("="*60)
                    print("✓ 收到响应！")
                    print("="*60)
                    print(f"响应时间: {elapsed:.3f}秒")
                    print()
                    print(f"AI建议: {response.get('action')}")
                    print(f"置信度: {response.get('confidence')}")
                    print(f"分析原因: {response.get('reason')}")
                    print(f"使用DeepSeek: {response.get('use_deepseek')}")
                    print()
                    print("✓ 优化版服务工作正常！")
                    
                    os.remove(response_file)
                    return True
                    
                except Exception as e:
                    print(f"读取响应错误: {e}")
                    if os.path.exists(response_file):
                        try:
                            os.remove(response_file)
                        except:
                            pass
            
            time.sleep(0.1)
            wait_count += 1
            if wait_count % 20 == 0:
                print(f"等待中... ({int(time.time() - start_time)}秒)")
        
        print()
        print("✗ 超时 - 未收到响应")
        print("请确认优化版服务正在运行！")
        return False
        
    except Exception as e:
        print(f"错误: {e}")
        if os.path.exists(request_file):
            try:
                os.remove(request_file)
            except:
                pass
        return False

if __name__ == "__main__":
    test_optimized_service()
    print()
    input("按回车键退出...")
