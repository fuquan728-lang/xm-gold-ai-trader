import sys
sys.path.append('.')
from core.mql5_data import get_mql5_data_manager
import json
import time

def test_mql5_data_update():
    """测试MQL5数据更新过程"""
    
    # 获取MQL5数据管理器
    manager = get_mql5_data_manager()
    
    print("1. 初始状态:")
    print(f"   保证金水平: {manager.account_info.margin_level}%")
    print(f"   余额: {manager.account_info.balance}")
    print(f"   净值: {manager.account_info.equity}")
    
    # 读取模拟数据文件
    print("\n2. 读取模拟数据文件...")
    try:
        with open('d:/MT5_Data/output.json', 'r', encoding='utf-8') as f:
            mql5_data = json.load(f)
        
        print(f"   文件中的保证金水平: {mql5_data['account']['margin_level']}%")
        print(f"   文件中的余额: {mql5_data['account']['balance']}")
        print(f"   文件中的净值: {mql5_data['account']['equity']}")
        
        # 构造MQL5数据格式
        update_data = {
            "type": "mql5_data",
            "account": mql5_data["account"],
            "positions": mql5_data.get("positions", []),
            "timestamp": time.time()
        }
        
        print("\n3. 更新MQL5数据...")
        success = manager.update_from_json(update_data)
        print(f"   更新结果: {success}")
        
        print("\n4. 更新后状态:")
        print(f"   保证金水平: {manager.account_info.margin_level}%")
        print(f"   余额: {manager.account_info.balance}")
        print(f"   净值: {manager.account_info.equity}")
        
        # 检查get_real_time_data_summary
        realtime = manager.get_real_time_data_summary()
        print("\n5. 实时数据摘要:")
        print(f"   保证金水平: {realtime['account_summary']['margin_level']}%")
        print(f"   余额: {realtime['account_summary']['balance']}")
        print(f"   净值: {realtime['account_summary']['equity']}")
        
        # 检查get_complete_broker_data
        complete = manager.get_complete_broker_data()
        print("\n6. 完整经纪商数据:")
        print(f"   保证金水平: {complete['account']['margin_level']}%")
        print(f"   余额: {complete['account']['balance']}")
        print(f"   净值: {complete['account']['equity']}")
        
        # 检查AI引擎看到的账户上下文
        from core.ai_engine import AIAnalyzer
        analyzer = AIAnalyzer()
        
        # 构建提示词查看账户上下文
        symbol = 'GOLD_'
        bid = 4698.53
        ask = 4699.0
        current_time = int(time.time())
        
        prompt = analyzer.build_prompt(symbol, bid, ask, current_time, include_account_context=True)
        
        # 提取账户上下文部分
        lines = prompt.split('\n')
        in_account_section = False
        print("\n7. AI引擎构建的提示词中的账户上下文:")
        for i, line in enumerate(lines):
            if '【账户实时状态 - 基于MQL5真实数据】' in line:
                in_account_section = True
                print(line)
            elif in_account_section and '【最终决策检查清单】' in line:
                print(line)
                break
            elif in_account_section:
                if i < len(lines) - 1 and i < 100:  # 限制输出
                    print(line)
        
        # 查找保证金水平数据
        import re
        for line in lines:
            if '保证金水平' in line:
                print(f"\n提示词中的保证金水平行: {line}")
                match = re.search(r'保证金水平:\s*(\d+\.?\d*)%', line)
                if match:
                    print(f"提取的保证金水平: {match.group(1)}%")
                
    except Exception as e:
        print(f"测试过程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mql5_data_update()