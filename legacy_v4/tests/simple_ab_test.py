#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版AI优化AB测试
对比优化前后AI交易决策准确率
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any
import numpy as np

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_engine import AIAnalyzer
from core.ai_engine_optimized import AIAnalyzerOptimized

def load_test_cases():
    """加载测试用例"""
    test_data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                 "performance_results.json")
    
    if not os.path.exists(test_data_path):
        print(f"测试数据文件不存在: {test_data_path}")
        return []
    
    try:
        with open(test_data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 从性能测试数据中提取测试用例
        test_records = data["test_results"]["with_mtf"]
        test_cases = []
        
        for i, record in enumerate(test_records[:10]):  # 使用前10个测试用例
            case_id = record.get("case_id", i)
            expected_action = record.get("expected", "HOLD")
            
            # 创建模拟数据
            test_case = {
                "case_id": case_id,
                "symbol": "XAUUSD",  # 黄金
                "bid": 1800.0 + np.random.uniform(-10, 10),
                "ask": 1800.5 + np.random.uniform(-10, 10),
                "current_time": datetime.now().timestamp(),
                "history": [],
                "indicators": {
                    "rsi": np.random.uniform(30, 70),
                    "macd": np.random.uniform(-0.01, 0.01),
                    "ema_20": 1800.0 + np.random.uniform(-10, 10),
                    "ema_50": 1805.0 + np.random.uniform(-10, 10),
                },
                "multi_timeframe": {
                    "h1": {"trend": "up" if np.random.random() > 0.5 else "down"},
                    "h4": {"trend": "up" if np.random.random() > 0.5 else "down"},
                    "d1": {"trend": "up" if np.random.random() > 0.5 else "down"}
                },
                "expected_action": expected_action
            }
            test_cases.append(test_case)
        
        return test_cases
        
    except Exception as e:
        print(f"加载测试用例失败: {e}")
        return []

def run_ab_test():
    """运行AB测试"""
    print("=" * 60)
    print("AI优化AB测试 - 简化版")
    print("=" * 60)
    
    # 初始化分析器
    original_analyzer = AIAnalyzer()
    optimized_analyzer = AIAnalyzerOptimized()
    
    # 加载测试用例
    test_cases = load_test_cases()
    if not test_cases:
        print("[FAIL] 无测试用例，测试终止")
        return
    
    print(f"[OK] 加载了 {len(test_cases)} 个测试用例")
    
    # 统计指标
    metrics = {
        "original": {"total": 0, "correct": 0, "hold_correct": 0, "hold_total": 0},
        "optimized": {"total": 0, "correct": 0, "hold_correct": 0, "hold_total": 0}
    }
    
    results = []
    
    # 运行测试
    for i, test_case in enumerate(test_cases):
        print(f"\n测试用例 {i+1}/{len(test_cases)}...")
        
        # 原始分析器
        try:
            original_action, original_confidence, original_reason = original_analyzer.get_fallback_strategy(
                test_case["symbol"], test_case["bid"], test_case["ask"],
                test_case["current_time"], test_case["history"],
                test_case["indicators"], test_case["multi_timeframe"]
            )
        except Exception as e:
            print(f"原始分析器错误: {e}")
            original_action, original_confidence, original_reason = "HOLD", 0.5, "分析失败"
        
        # 优化分析器
        try:
            optimized_action, optimized_confidence, optimized_reason = optimized_analyzer.analyze_market(
                test_case["symbol"], test_case["bid"], test_case["ask"],
                test_case["current_time"], test_case["history"],
                test_case["indicators"], test_case["multi_timeframe"]
            )
        except Exception as e:
            print(f"优化分析器错误: {e}")
            optimized_action, optimized_confidence, optimized_reason = "HOLD", 0.5, "分析失败"
        
        # 检查结果
        expected_action = test_case["expected_action"]
        correct_original = (original_action == expected_action)
        correct_optimized = (optimized_action == expected_action)
        
        # 更新统计
        metrics["original"]["total"] += 1
        metrics["original"]["correct"] += 1 if correct_original else 0
        if expected_action == "HOLD":
            metrics["original"]["hold_total"] += 1
            metrics["original"]["hold_correct"] += 1 if correct_original else 0
        
        metrics["optimized"]["total"] += 1
        metrics["optimized"]["correct"] += 1 if correct_optimized else 0
        if expected_action == "HOLD":
            metrics["optimized"]["hold_total"] += 1
            metrics["optimized"]["hold_correct"] += 1 if correct_optimized else 0
        
        # 记录结果
        result = {
            "case_id": test_case["case_id"],
            "expected_action": expected_action,
            "original_action": original_action,
            "original_correct": correct_original,
            "optimized_action": optimized_action,
            "optimized_correct": correct_optimized
        }
        results.append(result)
        
        print(f"  预期: {expected_action} | 原始: {original_action} ({correct_original}) | 优化: {optimized_action} ({correct_optimized})")
    
    # 计算结果
    print("\n" + "=" * 60)
    print("测试结果总结")
    print("=" * 60)
    
    if metrics["original"]["total"] > 0:
        original_accuracy = metrics["original"]["correct"] / metrics["original"]["total"] * 100
        print(f"原始分析器准确率: {original_accuracy:.1f}% ({metrics['original']['correct']}/{metrics['original']['total']})")
    
    if metrics["optimized"]["total"] > 0:
        optimized_accuracy = metrics["optimized"]["correct"] / metrics["optimized"]["total"] * 100
        print(f"优化分析器准确率: {optimized_accuracy:.1f}% ({metrics['optimized']['correct']}/{metrics['optimized']['total']})")
    
    if metrics["original"]["hold_total"] > 0:
        original_hold_accuracy = metrics["original"]["hold_correct"] / metrics["original"]["hold_total"] * 100
        print(f"原始分析器HOLD准确率: {original_hold_accuracy:.1f}% ({metrics['original']['hold_correct']}/{metrics['original']['hold_total']})")
    
    if metrics["optimized"]["hold_total"] > 0:
        optimized_hold_accuracy = metrics["optimized"]["hold_correct"] / metrics["optimized"]["hold_total"] * 100
        print(f"优化分析器HOLD准确率: {optimized_hold_accuracy:.1f}% ({metrics['optimized']['hold_correct']}/{metrics['optimized']['hold_total']})")
    
        # 计算改进
    if metrics["original"]["total"] > 0 and metrics["optimized"]["total"] > 0:
        original_accuracy = metrics["original"]["correct"] / metrics["original"]["total"] * 100
        optimized_accuracy = metrics["optimized"]["correct"] / metrics["optimized"]["total"] * 100
        improvement = optimized_accuracy - original_accuracy
        print(f"[IMPROVE] 总体准确率改进: {improvement:.1f}个百分点")
    
    # 保存结果
    output_path = os.path.join(os.path.dirname(__file__), "ab_test_results.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "test_cases_count": len(test_cases),
            "metrics": metrics,
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] 详细结果已保存到: {output_path}")
    return metrics

if __name__ == "__main__":
    run_ab_test()