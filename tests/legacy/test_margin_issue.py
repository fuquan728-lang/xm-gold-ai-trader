#!/usr/bin/env python3
"""
测试保证金水平0%问题
"""

import sys
import json
import time
from datetime import datetime

sys.path.append('.')

from core.ai_engine import AIAnalyzer
from core.mql5_data import get_mql5_data_manager
from core.logger import logger

def test_margin_data():
    """测试保证金数据流"""
    print("=== 测试保证金水平数据流 ===")
    
    # 1. 读取模拟数据文件
    with open('d:/MT5_Data/output.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print("1. 数据文件内容:")
    print(f"   保证金水平: {data['account']['margin_level']}%")
    print(f"   保证金: {data['account']['margin']}")
    print(f"   可用保证金: {data['account']['margin_free']}")
    
    # 2. 检查MQL5数据管理器
    manager = get_mql5_data_manager()
    print("\n2. MQL5数据管理器状态:")
    
    # 更新数据
    result = manager.update_from_json(data)
    print(f"   更新结果: {result}")
    
    # 检查实时数据摘要
    realtime = manager.get_real_time_data_summary()
    print(f"   实时数据保证金水平: {realtime['account_summary']['margin_level']}%")
    print(f"   实时数据保证金使用: {realtime['account_summary']['margin_used']}")
    print(f"   实时数据可用保证金: {realtime['account_summary']['margin_free']}")
    
    # 3. 测试AI引擎账户上下文构建
    analyzer = AIAnalyzer()
    symbol = 'GOLD_'
    bid = 4714.38
    ask = 4714.87
    current_time = int(time.time())
    
    print("\n3. AI引擎账户上下文构建:")
    
    # 获取账户上下文部分
    account_context = analyzer._build_account_context_section(symbol)
    
    # 检查保证金水平在上下文中的值
    lines = account_context.split('\n')
    for line in lines:
        if '保证金水平' in line:
            print(f"   账户上下文中的: {line.strip()}")
            # 提取数值
            import re
            match = re.search(r'保证金水平:\s*([0-9\.]+)%', line)
            if match:
                margin_level_in_context = float(match.group(1))
                print(f"   提取的保证金水平: {margin_level_in_context}%")
                if margin_level_in_context == 0.0:
                    print("   ⚠️ 问题发现: 账户上下文中的保证金水平为0%!")
    
    # 4. 检查实时数据获取方式
    print("\n4. 检查数据获取方式:")
    
    # 直接调用get_real_time_data_summary
    realtime2 = analyzer.mql5_data_manager.get_real_time_data_summary()
    margin_level_direct = realtime2['account_summary']['margin_level']
    print(f"   通过analyzer.mql5_data_manager获取: {margin_level_direct}%")
    
    # 5. 检查数据键名
    print("\n5. 检查数据键名:")
    account_summary = realtime['account_summary']
    for key, value in account_summary.items():
        print(f"   {key}: {value}")
    
    return account_context

def check_ai_decision():
    """检查AI决策过程"""
    print("\n=== 检查AI决策过程 ===")
    
    analyzer = AIAnalyzer()
    symbol = 'GOLD_'
    bid = 4714.38
    ask = 4714.87
    current_time = int(time.time())
    
    # 构建完整提示词
    prompt = analyzer.build_prompt(symbol, bid, ask, current_time, include_account_context=True)
    
    # 查找保证金相关信息
    lines = prompt.split('\n')
    for i, line in enumerate(lines):
        if '保证金水平' in line:
            print(f"提示词中的保证金信息: {line.strip()}")
            # 查看前后几行
            start = max(0, i-2)
            end = min(len(lines), i+3)
            for j in range(start, end):
                print(f"  {lines[j]}")

if __name__ == '__main__':
    test_margin_data()
    check_ai_decision()