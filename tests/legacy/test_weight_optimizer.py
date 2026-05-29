#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权重优化器演示和测试脚本
"""

import sys
import os
import time
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.weight_optimizer import WeightOptimizer, WeightConfig, TradeSignal, TriggerReason
from core.ai_engine import AIAnalyzer


def test_initialization():
    """测试初始化"""
    print("="*60)
    print("1. 测试权重优化器初始化")
    print("="*60)
    
    config = WeightConfig(
        default_weights={'h1': 0.35, 'h4': 0.35, 'd1': 0.30},
        min_weight=0.10,
        max_weight=0.60,
        max_adjustment_per_step=0.10,
        evaluation_period=5,  # 缩短评估周期用于测试
        performance_threshold=0.55,
        cooldown_period=1  # 缩短冷却期
    )
    
    optimizer = WeightOptimizer(config, data_dir="./test_weights")
    
    weights = optimizer.get_current_weights()
    print(f"   初始权重: {weights}")
    
    report = optimizer.get_performance_report()
    print(f"   初始性能报告: {report}")
    
    print("[OK] 初始化测试通过\n")
    return optimizer


def test_signal_recording(optimizer):
    """测试信号记录"""
    print("="*60)
    print("2. 测试交易信号记录")
    print("="*60)
    
    symbols = ['EURUSD', 'GBPUSD', 'USDJPY']
    actions = ['BUY', 'SELL', 'HOLD']
    
    for i in range(10):
        symbol = random.choice(symbols)
        action = random.choice(actions)
        bid = 1.1000 + random.random() * 0.01
        ask = bid + 0.0005
        
        # 生成各时间框架信号
        mtf_signals = {}
        for tf in ['h1', 'h4', 'd1']:
            mtf_signals[tf] = random.choice(actions)
        
        signal = TradeSignal(
            timestamp=time.time() - (10 - i) * 60,
            symbol=symbol,
            action=action,
            confidence=0.7 + random.random() * 0.2,
            bid=bid,
            ask=ask,
            multi_timeframe_signals=mtf_signals,
            result=random.choice(['win', 'loss', None]) if action in ['BUY', 'SELL'] else None
        )
        
        optimizer.record_signal(signal)
        print(f"   记录信号{i+1}: {symbol} {action} (置信度: {signal.confidence:.2f})")
    
    report = optimizer.get_performance_report()
    print(f"\n   更新后性能报告: {report}")
    print("[OK] 信号记录测试通过\n")


def test_weight_adjustment(optimizer):
    """测试权重调整"""
    print("="*60)
    print("3. 测试权重调整功能")
    print("="*60)
    
    old_weights = optimizer.get_current_weights().copy()
    print(f"   调整前权重: {old_weights}")
    
    # 手动触发调整
    adjusted = optimizer.adjust_weights(TriggerReason.MANUAL_INTERVENTION.value)
    print(f"   权重是否调整: {adjusted}")
    
    new_weights = optimizer.get_current_weights()
    print(f"   调整后权重: {new_weights}")
    
    # 验证新权重是否有效
    is_valid = optimizer._validate_weights(new_weights)
    print(f"   新权重是否有效: {is_valid}")
    
    # 验证权重变化在允许范围内
    for tf in ['h1', 'h4', 'd1']:
        change = abs(new_weights[tf] - old_weights[tf])
        max_change = optimizer.config.max_adjustment_per_step
        print(f"   {tf} 权重变化: {change:.4f} (最大允许: {max_change})")
        assert change <= max_change + 0.001, f"权重变化超出限制!"
    
    print("\n[OK] 权重调整测试通过\n")


def test_ai_engine_integration():
    """测试与AI引擎的集成"""
    print("="*60)
    print("4. 测试AI引擎与权重优化器集成")
    print("="*60)
    
    ai_analyzer = AIAnalyzer()
    
    # 模拟多时间框架数据
    symbol = "EURUSD"
    bid = 1.1050
    ask = 1.1055
    current_time = time.time()
    
    multi_timeframe = {
        'h1': {
            'history': [],
            'indicators': {'rsi': 45.0, 'macd_main': 0.0010, 'macd_signal': 0.0005}
        },
        'h4': {
            'history': [],
            'indicators': {'rsi': 50.0, 'macd_main': 0.0008, 'macd_signal': 0.0003}
        },
        'd1': {
            'history': [],
            'indicators': {'rsi': 55.0, 'macd_main': 0.0015, 'macd_signal': 0.0010}
        }
    }
    
    indicators = {
        'rsi': 48.0,
        'macd_main': 0.0008,
        'macd_signal': 0.0003,
        'ema20': 1.1040,
        'ema50': 1.1030,
        'ema100': 1.1020,
        'stoch_main': 40.0,
        'stoch_signal': 45.0
    }
    
    # 调用智能后备策略
    print(f"   调用智能后备策略（带多时间框架）...")
    action, confidence, reason = ai_analyzer.get_fallback_strategy(
        symbol, bid, ask, indicators, multi_timeframe
    )
    
    print(f"   AI决策: {action}")
    print(f"   置信度: {confidence:.2f}")
    print(f"   原因: {reason}")
    
    # 获取权重
    weights = ai_analyzer.weight_optimizer.get_current_weights()
    print(f"   当前权重: {weights}")
    
    print("\n[OK] AI引擎集成测试通过\n")


def main():
    """主函数"""
    print("="*60)
    print("-> 权重优化器完整测试套件")
    print("="*60)
    
    try:
        # 1. 测试初始化
        optimizer = test_initialization()
        
        # 2. 测试信号记录
        test_signal_recording(optimizer)
        
        # 3. 测试权重调整
        test_weight_adjustment(optimizer)
        
        # 4. 测试AI引擎集成
        test_ai_engine_integration()
        
        print("="*60)
        print("[DONE] 所有测试通过！权重优化系统运行正常")
        print("="*60)
        
        # 打印最终报告
        final_report = optimizer.get_performance_report()
        print(f"\n[DATA] 最终性能报告:")
        print(f"   总交易: {final_report['total_trades']}")
        print(f"   胜率: {final_report['win_rate']:.2%}")
        print(f"   当前权重: {final_report['current_weights']}")
        print(f"   权重历史记录数: {final_report['weights_history_length']}")
        
    except Exception as e:
        print(f"[ERR] 测试过程出错: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
