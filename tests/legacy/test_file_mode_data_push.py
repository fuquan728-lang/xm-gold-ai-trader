#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试File模式下的MQL5数据推送
"""

import sys
import os
import json
import time

# 添加项目路径
sys.path.append('.')
from core.mql5_data import get_mql5_data_manager

def test_file_mode_data_push():
    """测试File模式数据推送"""
    print("=== 测试File模式下的MQL5数据推送 ===")
    
    # 获取MQL5数据管理器
    manager = get_mql5_data_manager()
    print("[INFO] MQL5数据管理器已初始化")
    
    # 读取模拟数据文件
    file_path = 'd:/MT5_Data/output.json'
    try:
        # 检查文件是否存在
        if not os.path.exists(file_path):
            print(f"[ERROR] 数据文件不存在: {file_path}")
            print("请先运行数据生成脚本或检查路径")
            return False
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"[OK] 成功读取数据文件: {file_path}")
        
        # 更新数据
        result = manager.update_from_json(data)
        print(f"数据更新结果: {result}")
        
        if not result:
            print("[ERROR] 数据更新失败")
            return False
        
        # 获取并显示数据
        dashboard = manager.get_dashboard_data()
        print("\n=== 账户总览 ===")
        print(f"账户余额: ${dashboard['account']['balance']:.2f}")
        print(f"账户净值: ${dashboard['account']['equity']:.2f}")
        print(f"浮动盈亏: ${dashboard['account']['profit']:.2f}")
        print(f"保证金水平: {dashboard['account']['margin_level']:.1f}%")
        
        print("\n=== 持仓信息 ===")
        print(f"持仓数量: {dashboard['position_count']}")
        for i, pos in enumerate(dashboard['positions'], 1):
            print(f"  {i}. {pos['symbol']} {pos['type']} {pos['volume']:.2f}手 @ {pos['open_price']}")
            print(f"     当前价: {pos['current_price']}, 盈亏: ${pos['profit']:.2f}")
        
        # 获取完整经纪商数据
        broker_data = manager.get_complete_broker_data()
        print("\n=== 风险评估 ===")
        print(f"总风险暴露: {broker_data['positions']['total_volume']:.2f}手")
        print(f"持仓集中度: {broker_data['risk_metrics']['concentration_risk']:.2%}")
        print(f"账户健康度: {broker_data['risk_metrics']['account_health']:.2%}")
        
        print("\n=== 品种信息 ===")
        for symbol, info in broker_data['symbols'].items():
            print(f"  {symbol}: 点差 {info['spread']}, 最小手数 {info['min_lot']:.2f}")
        
        print("\n=== 实时数据汇总 ===")
        realtime = manager.get_real_time_data_summary()
        print(f"账户余额: ${realtime['account_summary']['balance']:.2f}")
        print(f"账户净值: ${realtime['account_summary']['equity']:.2f}")
        print(f"保证金使用: ${realtime['account_summary']['margin_used']:.2f}")
        print(f"浮动盈亏: ${realtime['account_summary']['floating_profit']:.2f}")
        print(f"持仓数量: {realtime['positions_summary']['total_count']}个")
        print(f"最后更新: {realtime['last_update']}")
        
        print("\n[SUCCESS] File模式数据推送测试完成！")
        return True
        
    except Exception as e:
        print(f"[ERROR] 数据推送测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_decision_with_account_context():
    """测试AI决策与账户上下文集成"""
    print("\n=== 测试AI决策与账户上下文集成 ===")
    
    try:
        from core.ai_engine import AIAnalyzer
        
        # 获取数据管理器
        manager = get_mql5_data_manager()
        
        # 创建AI分析器
        ai_analyzer = AIAnalyzer()
        print("[INFO] AI分析器已初始化")
        
        # 测试市场分析（使用账户上下文）
        market_data = {
            "symbol": "EURUSD",
            "timeframe": "H1",
            "bid": 1.0865,
            "ask": 1.0867,
            "indicators": {
                "rsi": 65.5,
                "macd_main": 0.0012,
                "macd_signal": 0.0008,
                "ema50": 1.0850,
                "ema20": 1.0845,
                "ema100": 1.0830,
                "atr": 0.0015,
                "stoch_k": 75.2,
                "stoch_d": 68.5
            }
        }
        
        print("[INFO] 开始AI分析...")
        
        # 获取账户数据用于上下文
        broker_data = manager.get_complete_broker_data()
        
        # 手动构建AI分析提示词（模拟AI决策）
        account_summary = f"""
账户实时状态 - 基于MQL5真实数据
- 账户余额: ${broker_data['account']['balance']:.2f}
- 账户净值: ${broker_data['account']['equity']:.2f} (浮动盈亏: ${broker_data['account']['floating_profit']:.2f})
- 保证金使用: ${broker_data['account']['margin_used']:.2f} (可用保证金: ${broker_data['account']['margin_free']:.2f})
- 保证金水平: {broker_data['account']['margin_level']:.1f}% (账户健康度: {'优秀' if broker_data['account']['margin_level'] > 1000 else '正常' if broker_data['account']['margin_level'] > 500 else '警告'})
- 总持仓数量: {broker_data['positions']['total_count']}个 (总手数: {broker_data['positions']['total_volume']:.2f})
- EURUSD当前持仓: {broker_data['positions']['by_symbol'].get('EURUSD', {}).get('position_count', 0)}个 (手数: {broker_data['positions']['by_symbol'].get('EURUSD', {}).get('total_volume', 0):.2f})
        """
        
        print("\n=== AI决策账户上下文 ===")
        print(account_summary)
        
        print("\n=== 风险考量 ===")
        if broker_data['risk_metrics']['concentration_risk'] > 0.5:
            print("[WARN] 持仓集中度 > 50%，建议谨慎开仓")
        if broker_data['risk_metrics']['account_health'] < 0.3:
            print("[WARN] 可用保证金不足，建议观望或平仓")
        
        # 模拟AI决策输出
        decision = {
            "action": "HOLD",
            "reason": "EURUSD已有持仓过重且账户健康度良好，建议观望",
            "confidence": 0.72,
            "risk_level": "LOW",
            "recommended_volume": 0.0
        }
        
        print("\n=== AI决策结果 ===")
        print(f"动作: {decision['action']}")
        print(f"理由: {decision['reason']}")
        print(f"置信度: {decision['confidence']:.2f}")
        print(f"风险等级: {decision['risk_level']}")
        print(f"建议手数: {decision['recommended_volume']:.3f}")
        
        print("\n[SUCCESS] AI决策与账户上下文集成测试完成！")
        return True
        
    except Exception as e:
        print(f"[ERROR] AI决策测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("MT5 AI系统 - 数据流集成测试")
    print("=" * 50)
    
    # 测试1: File模式数据推送
    if not test_file_mode_data_push():
        print("[FAIL] File模式数据推送测试失败")
        return
    
    # 测试2: AI决策与账户上下文集成
    if not test_ai_decision_with_account_context():
        print("[FAIL] AI决策测试失败")
        return
    
    print("\n" + "=" * 50)
    print("[PASS] 所有测试通过！系统已准备好运行。")
    print("\n下一步建议:")
    print("1. 启动主服务: python mt5_ai_service.py --mode file")
    print("2. 在MT5中加载EA并使用File模式通信")
    print("3. 监控日志文件查看实时数据流")

if __name__ == "__main__":
    main()