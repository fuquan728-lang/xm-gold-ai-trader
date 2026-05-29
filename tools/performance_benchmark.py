#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能基准测试工具
用于测试和比较原始版本和优化版本的性能差异
"""

import os
import sys
import time
import json
import random
import statistics
from datetime import datetime
from pathlib import Path

# 配置
TEST_DIR = Path(r"c:\Users\Administrator\Desktop\XM Global MT5\MQL5\Files")
NUM_TESTS = 10
SLEEP_INTERVAL = 0.1

# 测试数据
TEST_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
BASE_PRICES = {
    "XAUUSD": 2000.00,
    "EURUSD": 1.0800,
    "GBPUSD": 1.2600
}

class PerformanceTestResult:
    def __init__(self):
        self.times = []
        self.min_time = float('inf')
        self.max_time = 0
        self.total_time = 0
        self.success_count = 0
        self.fail_count = 0

def generate_test_request(symbol=None):
    """生成测试请求数据"""
    if symbol is None:
        symbol = random.choice(TEST_SYMBOLS)
    base_price = BASE_PRICES[symbol]
    
    variation = random.uniform(-5, 5)
    bid = base_price + variation
    ask = bid + 0.5
    
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "time": int(time.time()),
        "history": [
            {
                "time": int(time.time()) - 3600,
                "open": bid - 10,
                "high": bid + 5,
                "low": bid - 15,
                "close": bid - 5,
                "volume": 1000
            }
        ],
        "indicators": {
            "rsi": random.uniform(30, 70),
            "macd_main": random.uniform(-0.001, 0.001),
            "macd_signal": random.uniform(-0.001, 0.001),
            "ema50": bid
        }
    }

def run_single_test(request_file, response_file, test_data):
    """运行单次测试"""
    start_time = time.time()
    
    try:
        with open(request_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)
        
        wait_start = time.time()
        while time.time() - wait_start < 30:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-16') as f:
                        response = json.load(f)
                    os.remove(response_file)
                    elapsed = time.time() - start_time
                    return True, elapsed
                except:
                    pass
            time.sleep(SLEEP_INTERVAL)
        
        return False, time.time() - start_time
        
    except Exception as e:
        print(f"测试错误: {e}")
        if os.path.exists(request_file):
            try:
                os.remove(request_file)
            except:
                pass
        return False, time.time() - start_time

def run_benchmark(description):
    """运行基准测试"""
    print(f"\n{'='*60}")
    print(f" {description}")
    print(f"{'='*60}")
    print(f"测试次数: {NUM_TESTS}")
    print(f"开始时间: {datetime.now().strftime('%H:%M:%S')}")
    print()
    
    request_file = TEST_DIR / "ai_request.json"
    response_file = TEST_DIR / "ai_response.json"
    
    result = PerformanceTestResult()
    
    for i in range(NUM_TESTS):
        test_data = generate_test_request()
        print(f"测试 {i+1}/{NUM_TESTS}: {test_data['symbol']} @ {test_data['bid']:.2f}", end="")
        
        success, elapsed = run_single_test(request_file, response_file, test_data)
        
        if success:
            result.times.append(elapsed)
            result.total_time += elapsed
            result.success_count += 1
            if elapsed < result.min_time:
                result.min_time = elapsed
            if elapsed > result.max_time:
                result.max_time = elapsed
            print(f" - 成功 ({elapsed:.3f}s)")
        else:
            result.fail_count += 1
            print(f" - 失败")
        
        time.sleep(0.5)
    
    print()
    print_benchmark_results(result)
    return result

def print_benchmark_results(result):
    """打印基准测试结果"""
    print(f"测试完成时间: {datetime.now().strftime('%H:%M:%S')}")
    print()
    if result.success_count > 0:
        print(f"成功: {result.success_count}/{NUM_TESTS}")
        print(f"失败: {result.fail_count}/{NUM_TESTS}")
        print()
        print(f"平均响应时间: {statistics.mean(result.times):.3f}s")
        print(f"最小响应时间: {result.min_time:.3f}s")
        print(f"最大响应时间: {result.max_time:.3f}s")
        if len(result.times) >= 2:
            print(f"响应时间标准差: {statistics.stdev(result.times):.3f}s")
        print()
        print(f"总测试时间: {result.total_time:.3f}s")

def compare_results(original, optimized):
    """比较原始版本和优化版本的结果"""
    print(f"\n{'='*60}")
    print(f"性能对比分析")
    print(f"{'='*60}")
    
    if original.success_count > 0 and optimized.success_count > 0:
        orig_avg = statistics.mean(original.times)
        opt_avg = statistics.mean(optimized.times)
        
        improvement = ((orig_avg - opt_avg) / orig_avg) * 100
        
        print(f"原始版本平均响应时间: {orig_avg:.3f}s")
        print(f"优化版本平均响应时间: {opt_avg:.3f}s")
        print()
        print(f"性能提升: {improvement:+.1f}%")
        
        if improvement > 0:
            print(f"✓ 优化成功！响应时间减少了 {improvement:.1f}%")
        else:
            print(f"[WARN] 优化效果不明显或性能有所下降")
        
        print()
        print(f"原始版本最小响应时间: {original.min_time:.3f}s → {original.max_time:.3f}s")
        print(f"优化版本最小响应时间: {optimized.min_time:.3f}s → {optimized.max_time:.3f}s")
        
        print()
        print(f"原始版本成功数: {original.success_count}/{NUM_TESTS}")
        print(f"优化版本成功数: {optimized.success_count}/{NUM_TESTS}")

def main():
    """主函数"""
    print("="*60)
    print("MT5 AI交易服务 - 性能基准测试工具")
    print("="*60)
    print()
    
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    
    print("请选择要运行的测试:")
    print("1. 仅测试优化版本")
    print("2. 对比原始版本和优化版本")
    print("3. 退出")
    print()
    
    choice = input("请输入选择 (1-3): ").strip()
    
    if choice == "1":
        print("\n正在启动优化版本测试...")
        print("请确保优化版本服务正在运行！")
        input("按回车键继续...")
        optimized_result = run_benchmark("优化版本性能测试")
        
    elif choice == "2":
        print("\n请按照以下步骤进行对比测试:")
        print("1. 首先启动原始版本服务")
        input("按回车键开始原始版本测试...")
        
        original_result = run_benchmark("原始版本性能测试")
        
        print("\n现在请启动优化版本服务")
        input("按回车键开始优化版本测试...")
        
        optimized_result = run_benchmark("优化版本性能测试")
        
        compare_results(original_result, optimized_result)
        
    else:
        print("退出")
        return
    
    print("\n测试完成！")

if __name__ == "__main__":
    main()
