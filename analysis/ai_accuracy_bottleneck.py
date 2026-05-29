#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI交易准确率瓶颈分析
分析performance_results.json文件，找出准确率低的原因
"""

import json
import os
from typing import Dict, List, Any
from collections import defaultdict

def load_performance_data():
    """加载性能测试数据"""
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "performance_results.json")
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def analyze_accuracy_bottleneck(data):
    """分析准确率瓶颈"""
    print("=== AI交易准确率瓶颈分析报告 ===\n")
    
    # 1. 总体准确率分析
    analysis = data.get("analysis", {})
    without_mtf_acc = analysis.get("without_mtf_accuracy", 0)
    with_mtf_acc = analysis.get("with_mtf_accuracy", 0)
    improvement = analysis.get("improvement", 0)
    
    print(f"1. 总体准确率:")
    print(f"   - 无多时间框架: {without_mtf_acc:.1f}%")
    print(f"   - 有多时间框架: {with_mtf_acc:.1f}%")
    print(f"   - 提升效果: {improvement:.1f}个百分点\n")
    
    # 2. 错误类型分析
    test_groups = ["without_mtf", "with_mtf"]
    
    for group in test_groups:
        print(f"2. {group} 错误类型分析:")
        records = data["test_results"].get(group, [])
        
        # 统计错误类型
        error_patterns = defaultdict(int)
        action_distribution = defaultdict(lambda: {"total": 0, "correct": 0})
        
        for record in records:
            action = record.get("action", "UNKNOWN")
            expected = record.get("expected", "UNKNOWN")
            correct = record.get("correct", False)
            
            # 更新action分布
            action_distribution[action]["total"] += 1
            if correct:
                action_distribution[action]["correct"] += 1
            
            # 错误类型分析
            if not correct:
                error_type = f"{action}->{expected}"
                error_patterns[error_type] += 1
        
        print(f"   - 总测试数: {len(records)}")
        print(f"   - 正确数: {sum(1 for r in records if r.get('correct', False))}")
        print(f"   - 错误数: {sum(1 for r in records if not r.get('correct', False))}")
        
        # 打印错误类型分布（前5名）
        if error_patterns:
            sorted_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)
            print(f"   - 常见错误类型:")
            for error_type, count in sorted_errors[:5]:
                percentage = count / len(records) * 100
                print(f"     {error_type}: {count}次 ({percentage:.1f}%)")
        
        # 打印action准确率
        print(f"   - 操作类型准确率:")
        for action, stats in action_distribution.items():
            if stats["total"] > 0:
                acc = stats["correct"] / stats["total"] * 100
                print(f"     {action}: {acc:.1f}% ({stats['correct']}/{stats['total']})")
        
        print()
    
    # 3. 置信度分析
    print("3. 置信度与准确率关系分析:")
    
    for group in test_groups:
        records = data["test_results"].get(group, [])
        
        # 按置信度分组
        confidence_buckets = defaultdict(lambda: {"total": 0, "correct": 0})
        
        for record in records:
            confidence = record.get("confidence", 0.5)
            bucket = round(confidence * 10) / 10  # 四舍五入到0.1
            
            confidence_buckets[bucket]["total"] += 1
            if record.get("correct", False):
                confidence_buckets[bucket]["correct"] += 1
        
        print(f"   {group}:")
        for bucket in sorted(confidence_buckets.keys()):
            stats = confidence_buckets[bucket]
            if stats["total"] > 0:
                acc = stats["correct"] / stats["total"] * 100
                print(f"     置信度 {bucket:.1f}: {acc:.1f}% ({stats['correct']}/{stats['total']})")
        print()
    
    # 4. 错误案例分析
    print("4. 典型错误案例（置信度高但错误的交易）:")
    
    for group in test_groups:
        records = data["test_results"].get(group, [])
        
        high_confidence_errors = []
        for record in records:
            if not record.get("correct", False) and record.get("confidence", 0) > 0.7:
                high_confidence_errors.append(record)
        
        print(f"   {group}中置信度>0.7但错误的交易: {len(high_confidence_errors)}个")
        if high_confidence_errors[:3]:  # 显示前3个
            print("   示例:")
            for error in high_confidence_errors[:3]:
                print(f"     案例{error.get('case_id')}: {error.get('action')}->{error.get('expected')}, "
                      f"置信度{error.get('confidence'):.3f}, 原因: {error.get('reason', 'N/A')}")
        print()
    
    return {
        "without_mtf_accuracy": without_mtf_acc,
        "with_mtf_accuracy": with_mtf_acc,
        "improvement": improvement,
        "error_patterns": dict(error_patterns) if 'error_patterns' in locals() else {}
    }

def generate_recommendations(analysis_results):
    """生成优化建议"""
    print("=== 优化建议 ===\n")
    
    acc_with_mtf = analysis_results["with_mtf_accuracy"]
    error_patterns = analysis_results.get("error_patterns", {})
    
    print("1. 核心问题识别:")
    if acc_with_mtf < 60:
        print("   [OK] 主要问题: AI决策准确率过低（<60%），需要系统性优化")
    else:
        print("   [WARN]️ 次要问题: 准确率有提升空间")
    
    # 分析常见错误类型
    if error_patterns:
        most_common_errors = sorted(error_patterns.items(), key=lambda x: x[1], reverse=True)[:3]
        print("   [OK] 常见错误模式:")
        for error_type, count in most_common_errors:
            print(f"     - {error_type}: 发生{count}次")
    
    print("\n2. 优化方向:")
    
    if "BUY->SELL" in error_patterns or "SELL->BUY" in error_patterns:
        print("   🔄 方向判断错误: 需要增强趋势识别能力")
        print("     建议: 增加MACD、布林带等趋势指标")
    
    if "BUY->HOLD" in error_patterns or "SELL->HOLD" in error_patterns:
        print("   [WARN]️ 过度交易问题: 在应该观望时开仓")
        print("     建议: 增加震荡市场识别，优化HOLD决策逻辑")
    
    if "HOLD->BUY" in error_patterns or "HOLD->SELL" in error_patterns:
        print("   [WARN]️ 保守过度问题: 错过交易机会")
        print("     建议: 降低开仓阈值，优化信号确认机制")
    
    print("\n3. 技术改进措施:")
    print("   a. 提示词优化:")
    print("      - 增加更多技术指标分析逻辑")
    print("      - 强化风险管理上下文")
    print("      - 集成市场情绪分析")
    
    print("   b. 数据增强:")
    print("      - 添加宏观经济数据")
    print("      - 集成资金流向数据")
    print("      - 增加新闻情感分析")
    
    print("   c. 模型优化:")
    print("      - 实现历史学习反馈机制")
    print("      - 动态调整置信度阈值")
    print("      - 集成多时间框架共振分析")
    
    print("   d. 测试验证:")
    print("      - 建立更全面的测试数据集")
    print("      - 实现AB测试框架")
    print("      - 定期评估和调优")

def main():
    """主函数"""
    print("开始分析AI交易准确率瓶颈...\n")
    
    try:
        # 加载数据
        data = load_performance_data()
        
        # 分析瓶颈
        analysis_results = analyze_accuracy_bottleneck(data)
        
        # 生成建议
        generate_recommendations(analysis_results)
        
        print("分析完成！")
        
    except Exception as e:
        print(f"分析过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()