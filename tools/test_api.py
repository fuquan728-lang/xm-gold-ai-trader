#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试DeepSeek API集成
"""

import requests
import json
from datetime import datetime

def test_trade_api():
    """测试交易API"""
    url = "http://localhost:8000/api/trade"
    
    data = {
        "symbol": "XAUUSD",
        "bid": 2000.00,
        "ask": 2000.50,
        "time": int(datetime.now().timestamp())
    }
    
    print("=" * 60)
    print("测试DeepSeek交易API")
    print("=" * 60)
    print(f"请求数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(url, json=data, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        print("=" * 60)
        print("AI响应:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print()
        
        if result.get("use_deepseek"):
            print("[OK] DeepSeek AI调用成功！")
        else:
            print("[WARN] 使用随机策略")
            
    except Exception as e:
        print(f"[ERR] 错误: {str(e)}")

if __name__ == "__main__":
    test_trade_api()
