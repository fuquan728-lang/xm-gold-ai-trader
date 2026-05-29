import sys
sys.path.append('.')
from core.mql5_data import get_mql5_data_manager
from core.risk_manager import RiskManager
from core.margin_manager import MarginManager
import json
import time

def test_risk_manager_margin_logic():
    """测试风险管理器中的保证金逻辑"""
    
    print("=== 测试风险管理器保证金警告问题 ===\n")
    
    # 获取MQL5数据管理器
    mql5_manager = get_mql5_data_manager()
    
    # 读取模拟数据文件
    with open('d:/MT5_Data/output.json', 'r', encoding='utf-8') as f:
        mql5_data = json.load(f)
    
    # 更新MQL5数据
    update_data = {
        "type": "mql5_data",
        "account": mql5_data["account"],
        "positions": mql5_data.get("positions", []),
        "timestamp": time.time()
    }
    success = mql5_manager.update_from_json(update_data)
    print(f"1. MQL5数据更新结果: {success}")
    
    # 获取实时数据
    realtime_data = mql5_manager.get_real_time_data_summary()
    account_summary = realtime_data.get("account_summary", {})
    
    print(f"2. 实时账户数据:")
    print(f"   保证金水平: {account_summary.get('margin_level', 0.0)}%")
    print(f"   余额: {account_summary.get('balance', 0.0)}")
    print(f"   净值: {account_summary.get('equity', 0.0)}")
    
    # 创建风险管理器
    risk_manager = RiskManager(account_balance=10000.0)
    
    # 测试保证金管理器
    margin_manager = MarginManager()
    
    symbol = "GOLD_"
    position_size = 0.01
    current_price = 4698.53
    
    print(f"\n3. 测试保证金管理器建议:")
    try:
        advice = margin_manager.get_margin_advice_for_trade(symbol, position_size, current_price)
        print(f"   保证金水平: {advice.get('margin_level', 0.0)}%")
        print(f"   警告级别: {advice.get('warning_level', 'unknown')}")
        print(f"   消息: {advice.get('message', '无')}")
    except Exception as e:
        print(f"   获取保证金建议出错: {e}")
    
    # 测试风险管理器风险评估
    print(f"\n4. 测试风险管理器风险评估:")
    try:
        assessment = risk_manager.assess_trade_risk_with_real_data(
            symbol=symbol,
            action="SELL",
            confidence=0.68,
            current_price=current_price
        )
        
        print(f"   风险评分: {assessment.risk_score}")
        print(f"   风险等级: {assessment.risk_level}")
        print(f"   警告消息: {assessment.warning_messages}")
        
        # 检查警告消息
        for warning in assessment.warning_messages:
            if "保证金水平" in warning:
                print(f"   ✅ 找到保证金警告: {warning}")
                if "0.0%" in warning:
                    print(f"   ❗ 发现0.0%警告问题!")
            elif "保证金" in warning:
                print(f"   💡 相关保证金消息: {warning}")
                
    except Exception as e:
        print(f"   风险评估出错: {e}")
        import traceback
        traceback.print_exc()
    
    # 检查风险管理器的内部数据
    print(f"\n5. 检查风险管理器内部数据:")
    
    # 尝试直接调用保证金管理器获取建议
    try:
        print(f"   risk_manager.margin_manager: {risk_manager.margin_manager}")
        
        # 测试风险管理器使用的保证金管理器
        if hasattr(risk_manager, 'margin_manager'):
            mgr = risk_manager.margin_manager
            advice2 = mgr.get_margin_advice_for_trade(symbol, position_size, current_price)
            print(f"   风险管理器获取的保证金建议:")
            print(f"     保证金水平: {advice2.get('margin_level', 0.0)}%")
            print(f"     警告级别: {advice2.get('warning_level', 'unknown')}")
            print(f"     消息: {advice2.get('message', '无')}")
            
            # 检查数据是否正确
            if advice2.get('margin_level', 0.0) == 0.0:
                print(f"   ❗ 风险管理器返回的保证金水平为0.0%，这是问题来源!")
            else:
                print(f"   ✅ 风险管理器返回的保证金水平正常: {advice2.get('margin_level', 0.0)}%")
    except Exception as e:
        print(f"   检查风险管理器内部数据出错: {e}")
    
    print(f"\n6. 诊断总结:")
    print(f"   - MQL5数据管理器中的保证金水平: {account_summary.get('margin_level', 0.0)}%")
    print(f"   - 如果风险管理器显示0.0%，可能是数据同步问题")
    print(f"   - 检查风险管理器是否使用了正确的数据源")

if __name__ == "__main__":
    test_risk_manager_margin_logic()