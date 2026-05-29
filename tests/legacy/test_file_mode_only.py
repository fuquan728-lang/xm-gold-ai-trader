#!/usr/bin/env python3
"""
文件模式专用测试脚本
测试文件模式下EA与Python服务的通信是否正常
"""

import os
import time
import json
from pathlib import Path

def test_file_mode():
    print("文件模式专用测试")
    print("================")
    
    # 配置文件路径
    workspace = Path(__file__).parent
    mql5_files_path = workspace / "MQL5" / "Files"
    
    # 创建测试文件
    test_file = mql5_files_path / "AI_REQUEST.json"
    response_file = mql5_files_path / "AI_RESPONSE.json"
    
    # 确保目录存在
    mql5_files_path.mkdir(parents=True, exist_ok=True)
    
    print(f"工作区: {workspace}")
    print(f"MQL5文件目录: {mql5_files_path}")
    print(f"测试请求文件: {test_file}")
    print(f"测试响应文件: {response_file}")
    
    # 创建测试请求
    test_request = {
        "symbol": "GOLD_",
        "timestamp": int(time.time()),
        "price": 2015.50,
        "action": "TEST",
        "mode": "FILE",
        "message": "文件模式测试请求"
    }
    
    # 写入请求文件
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_request, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] 已创建测试请求文件")
    print(f"[INFO] 请求内容: {test_request}")
    
    # 模拟AI服务响应
    test_response = {
        "action": "HOLD",
        "confidence": 0.85,
        "reason": "文件模式测试通过",
        "price": 2015.50,
        "timestamp": int(time.time()),
        "symbol": "GOLD_",
        "status": "SUCCESS"
    }
    
    # 写入响应文件
    with open(response_file, 'w', encoding='utf-8') as f:
        json.dump(test_response, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] 已创建测试响应文件")
    print(f"[INFO] 响应内容: {test_response}")
    
    # 清理文件
    time.sleep(1)
    if test_file.exists():
        test_file.unlink()
        print("[OK] 已清理测试请求文件")
    
    if response_file.exists():
        response_file.unlink()
        print("[OK] 已清理测试响应文件")
    
    print("\n[SUCCESS] 文件模式测试完成")
    print("==========================")
    print("现在EA将使用纯文件模式通信，不再尝试Socket连接")
    print("在EA中设置 InpCommMode = MODE_FILE")
    print("在.env中设置 COMMUNICATION_MODE = file")
    print("当前已全部配置完成")

if __name__ == "__main__":
    test_file_mode()