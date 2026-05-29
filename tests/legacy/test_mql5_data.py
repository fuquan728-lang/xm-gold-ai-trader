#!/usr/bin/env python3
"""
MQL5 数据集成 - 测试脚本
模拟 EA 向服务器推送账户、持仓数据
"""
import sys
import json
import socket
import time
import random
from datetime import datetime

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from core.mql5_data import get_mql5_data_manager
from core.logger import setup_logger, logger

def generate_mock_data():
    """生成模拟数据"""
    balance = 10000 + random.uniform(-500, 500)
    profit = random.uniform(-200, 300)
    equity = balance + profit
    
    positions = []
    pos_count = random.randint(0, 3)
    
    for i in range(pos_count):
        pos = {
            "ticket": int(1234500 + i),
            "symbol": random.choice(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]),
            "type": random.choice(["BUY", "SELL"]),
            "volume": round(random.uniform(0.1, 1.0), 2),
            "open_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "open_price": 1.08 + random.uniform(-0.05, 0.05),
            "sl": 0.0,
            "tp": 0.0,
            "current_price": 1.08 + random.uniform(-0.05, 0.05),
            "profit": round(random.uniform(-50, 100), 2),
            "swap": 0.0,
            "comment": "AI Test"
        }
        positions.append(pos)
    
    return {
        "type": "mql5_data",
        "account": {
            "balance": balance,
            "equity": equity,
            "margin": balance * 0.1,
            "margin_free": balance * 0.9,
            "margin_level": 1000.0,
            "profit": profit,
            "currency": "USD",
            "leverage": 100,
            "account": 1234567,
            "server": "DemoServer"
        },
        "positions": positions,
        "history": []
    }

def send_data_to_server(data, host="127.0.0.1", port=8080):
    """发送数据到 Socket 服务器"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        json_str = json.dumps(data, ensure_ascii=False) + "\n"
        sock.sendall(json_str.encode('utf-8'))
        
        try:
            response = sock.recv(4096)
            if response:
                logger.info(f"📥 服务器响应: {response.decode('utf-8').strip()}")
        except socket.timeout:
            pass
        
        sock.close()
        return True
    except Exception as e:
        logger.error(f"[ERR] 发送数据失败: {e}")
        return False

def test_local_update():
    """测试本地数据更新（不通过网络）"""
    print("=" * 70)
    print("测试本地 MQL5 数据管理")
    print("=" * 70)
    
    manager = get_mql5_data_manager()
    
    for i in range(3):
        print(f"\n[DATA] 第 {i+1} 次数据更新...")
        data = generate_mock_data()
        success = manager.update_from_json(data)
        
        if success:
            print("[OK] 数据更新成功")
            dashboard_data = manager.get_dashboard_data()
            print(f"   账户净值: {dashboard_data['account']['equity']:.2f}")
            print(f"   浮动盈亏: {dashboard_data['account']['profit']:.2f}")
            print(f"   持仓数量: {dashboard_data['position_count']}")
            print(f"   总持仓盈亏: {dashboard_data['total_position_profit']:.2f}")
        
        time.sleep(1)

def test_socket_update():
    """测试 Socket 推送数据"""
    print("\n" + "=" * 70)
    print("测试 Socket 数据推送")
    print("=" * 70)
    print("[WARN]  请确保 mt5_ai_service.py 正在运行\n")
    
    for i in range(3):
        print(f"\n[DATA] 第 {i+1} 次数据推送...")
        data = generate_mock_data()
        success = send_data_to_server(data)
        
        if success:
            print("[OK] 数据推送成功")
        
        time.sleep(2)

if __name__ == "__main__":
    logger = setup_logger(level=20)
    
    print("\n选择测试模式:")
    print("  1. 本地数据管理测试")
    print("  2. Socket 数据推送测试")
    print("  3. 两者都测试")
    
    choice = input("\n请选择 (1/2/3): ").strip()
    
    if choice == "1":
        test_local_update()
    elif choice == "2":
        test_socket_update()
    elif choice == "3":
        test_local_update()
        test_socket_update()
    else:
        print("无效选择")
