#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Socket通信性能基准测试
第1阶段原型验证：比较Socket模式与文件模式的性能差异

测试指标：
1. 端到端延迟（请求发送到响应接收）
2. 吞吐量（每秒处理请求数）
3. 成功率
4. 并发处理能力
"""

import os
import sys
import time
import json
import socket
import threading
import statistics
from datetime import datetime
from typing import List, Dict, Any, Tuple
import random

# 测试配置
SOCKET_HOST = "127.0.0.1"
SOCKET_PORT = 8080
NUM_REQUESTS = 20  # 总请求数
CONCURRENT_REQUESTS = 3  # 并发请求数
REQUEST_TIMEOUT = 10.0  # 请求超时时间（秒）

# 测试数据
TEST_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD"]
BASE_PRICES = {
    "XAUUSD": 2000.00,
    "EURUSD": 1.0800,
    "GBPUSD": 1.2600
}

class TestResult:
    """测试结果类"""
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.times = []  # 每次请求的耗时（秒）
        self.success_count = 0
        self.fail_count = 0
        self.errors = []
        self.start_time = 0
        self.end_time = 0
        
    def add_result(self, success: bool, elapsed: float, error: str = ""):
        if success:
            self.times.append(elapsed)
            self.success_count += 1
        else:
            self.fail_count += 1
            if error:
                self.errors.append(error)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.times:
            return {
                "total_requests": self.success_count + self.fail_count,
                "success_count": self.success_count,
                "fail_count": self.fail_count,
                "success_rate": 0.0,
                "avg_time": 0.0,
                "min_time": 0.0,
                "max_time": 0.0,
                "std_dev": 0.0,
                "total_time": 0.0,
                "throughput": 0.0
            }
        
        total_time = self.end_time - self.start_time if self.end_time > self.start_time else sum(self.times)
        
        return {
            "total_requests": self.success_count + self.fail_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "success_rate": (self.success_count / (self.success_count + self.fail_count)) * 100,
            "avg_time": statistics.mean(self.times),
            "min_time": min(self.times),
            "max_time": max(self.times),
            "std_dev": statistics.stdev(self.times) if len(self.times) >= 2 else 0.0,
            "total_time": total_time,
            "throughput": self.success_count / total_time if total_time > 0 else 0.0
        }

def generate_test_request() -> Dict[str, Any]:
    """生成测试请求数据"""
    symbol = random.choice(TEST_SYMBOLS)
    base_price = BASE_PRICES[symbol]
    
    variation = random.uniform(-5, 5) / 100  # 小范围波动
    bid = base_price + variation
    ask = bid + 0.0005
    
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "time": int(time.time()),
        "history": [
            {
                "time": int(time.time()) - 3600,
                "open": bid - 0.0010,
                "high": bid + 0.0020,
                "low": bid - 0.0020,
                "close": bid - 0.0005,
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

def send_socket_request(request_data: Dict[str, Any]) -> Tuple[bool, float, str]:
    """发送Socket请求并测量时间"""
    start_time = time.time()
    
    try:
        # 创建Socket连接
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.settimeout(REQUEST_TIMEOUT)
        client_socket.connect((SOCKET_HOST, SOCKET_PORT))
        
        # 发送请求
        request_json = json.dumps(request_data) + '\n'
        client_socket.sendall(request_json.encode('utf-8'))
        
        # 接收响应
        response = b""
        while True:
            chunk = client_socket.recv(4096)
            if not chunk:
                break
            response += chunk
            if b'\n' in response:
                break
        
        client_socket.close()
        
        # 解析响应
        response_str = response.decode('utf-8').strip()
        response_data = json.loads(response_str)
        
        elapsed = time.time() - start_time
        
        # 验证响应
        if 'action' not in response_data:
            return False, elapsed, "响应缺少action字段"
        
        return True, elapsed, ""
        
    except socket.timeout:
        elapsed = time.time() - start_time
        return False, elapsed, f"请求超时（{REQUEST_TIMEOUT}秒）"
    except ConnectionRefusedError:
        elapsed = time.time() - start_time
        return False, elapsed, "连接被拒绝，请确保服务器正在运行"
    except Exception as e:
        elapsed = time.time() - start_time
        return False, elapsed, f"请求失败: {str(e)}"

def run_single_thread_test(thread_id: int, num_requests: int, result: TestResult):
    """运行单线程测试"""
    for i in range(num_requests):
        request_data = generate_test_request()
        
        success, elapsed, error = send_socket_request(request_data)
        
        result.add_result(success, elapsed, error)
        
        if success:
            print(f"  线程{thread_id}: 请求{i+1}/{num_requests} - 成功 ({elapsed:.3f}s)")
        else:
            print(f"  线程{thread_id}: 请求{i+1}/{num_requests} - 失败: {error} ({elapsed:.3f}s)")
        
        # 请求间小延迟，模拟真实场景
        time.sleep(0.1)

def run_concurrent_test(num_requests: int, concurrent_threads: int) -> TestResult:
    """运行并发测试"""
    print(f"-> 开始并发测试: {num_requests}个请求，{concurrent_threads}个并发线程")
    
    result = TestResult("Socket并发测试")
    result.start_time = time.time()
    
    # 计算每个线程的请求数
    requests_per_thread = num_requests // concurrent_threads
    remaining = num_requests % concurrent_threads
    
    threads = []
    thread_results = []
    
    # 创建线程
    for i in range(concurrent_threads):
        thread_requests = requests_per_thread + (1 if i < remaining else 0)
        if thread_requests == 0:
            continue
            
        thread_result = TestResult(f"线程{i}")
        thread_results.append(thread_result)
        
        thread = threading.Thread(
            target=run_single_thread_test,
            args=(i, thread_requests, thread_result)
        )
        threads.append(thread)
    
    # 启动所有线程
    for thread in threads:
        thread.start()
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    # 合并结果
    for thread_result in thread_results:
        result.times.extend(thread_result.times)
        result.success_count += thread_result.success_count
        result.fail_count += thread_result.fail_count
        result.errors.extend(thread_result.errors)
    
    result.end_time = time.time()
    
    return result

def run_sequential_test(num_requests: int) -> TestResult:
    """运行顺序测试（无并发）"""
    print(f"[TEST] 开始顺序测试: {num_requests}个请求")
    
    result = TestResult("Socket顺序测试")
    result.start_time = time.time()
    
    for i in range(num_requests):
        request_data = generate_test_request()
        
        success, elapsed, error = send_socket_request(request_data)
        
        result.add_result(success, elapsed, error)
        
        if success:
            print(f"  请求{i+1}/{num_requests} - 成功 ({elapsed:.3f}s)")
        else:
            print(f"  请求{i+1}/{num_requests} - 失败: {error} ({elapsed:.3f}s)")
        
        # 请求间小延迟
        time.sleep(0.2)
    
    result.end_time = time.time()
    
    return result

def print_test_result(result: TestResult):
    """打印测试结果"""
    stats = result.get_stats()
    
    print("\n" + "="*70)
    print(f"测试结果: {result.test_name}")
    print("="*70)
    print(f"总请求数: {stats['total_requests']}")
    print(f"成功: {stats['success_count']}")
    print(f"失败: {stats['fail_count']}")
    print(f"成功率: {stats['success_rate']:.1f}%")
    print()
    
    if stats['success_count'] > 0:
        print("性能指标:")
        print(f"  平均响应时间: {stats['avg_time']*1000:.1f}ms")
        print(f"  最小响应时间: {stats['min_time']*1000:.1f}ms")
        print(f"  最大响应时间: {stats['max_time']*1000:.1f}ms")
        print(f"  响应时间标准差: {stats['std_dev']*1000:.1f}ms")
        print(f"  总测试时间: {stats['total_time']:.2f}s")
        print(f"  吞吐量: {stats['throughput']:.2f} 请求/秒")
    
    if result.errors:
        print(f"\n错误列表 (前5个):")
        for error in result.errors[:5]:
            print(f"  • {error}")
        if len(result.errors) > 5:
            print(f"  ... 还有 {len(result.errors)-5} 个错误")
    
    print("="*70)

def compare_with_file_mode():
    """与文件模式性能对比（基于文档数据）"""
    print("\n" + "="*70)
    print("Socket模式 vs 文件模式性能对比")
    print("="*70)
    
    # 从PERFORMANCE_OPTIMIZATION_GUIDE.md获取的基准数据
    file_mode_stats = {
        "avg_response_time": 2.345,  # 秒（来自文档示例）
        "min_response_time": 0.5,     # 估计值
        "max_response_time": 10.0,    # 文档中提到最长阻塞10秒
        "cpu_usage_idle": 5.0,        # 空闲时CPU占用（%）
        "cpu_usage_active": 15.0,     # 活动时CPU占用（%）
        "communication_method": "文件轮询",
        "blocking_time": 10.0         # 最长阻塞时间（秒）
    }
    
    print("文件模式（基于项目文档）:")
    print(f"  • 平均响应时间: {file_mode_stats['avg_response_time']*1000:.1f}ms")
    print(f"  • 响应时间范围: {file_mode_stats['min_response_time']*1000:.1f}ms - {file_mode_stats['max_response_time']*1000:.1f}ms")
    print(f"  • 最长阻塞时间: {file_mode_stats['blocking_time']:.1f}秒")
    print(f"  • CPU占用（空闲）: {file_mode_stats['cpu_usage_idle']:.1f}%")
    print(f"  • CPU占用（活动）: {file_mode_stats['cpu_usage_active']:.1f}%")
    print(f"  • 通信方式: {file_mode_stats['communication_method']}")
    
    print("\nSocket模式（目标性能）:")
    print("  • 平均响应时间: < 100ms")
    print("  • 响应时间范围: 10ms - 200ms")
    print("  • 阻塞时间: 无（异步处理）")
    print("  • CPU占用（空闲）: < 0.5%")
    print("  • CPU占用（活动）: < 5%")
    print("  • 通信方式: TCP套接字")
    
    print("\n预期改进:")
    print("  • 延迟降低: > 90%")
    print("  • CPU占用减少: > 50%")
    print("  • 可靠性提升: 消除竞态条件")
    print("  • 可扩展性: 支持多并发连接")
    print("="*70)

def check_server_availability():
    """检查服务器是否可用"""
    print("[TEST] 检查服务器可用性...")
    
    try:
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.settimeout(2.0)
        test_socket.connect((SOCKET_HOST, SOCKET_PORT))
        test_socket.close()
        print(f"[OK] 服务器 {SOCKET_HOST}:{SOCKET_PORT} 可用")
        return True
    except ConnectionRefusedError:
        print(f"[ERR] 无法连接到服务器 {SOCKET_HOST}:{SOCKET_PORT}")
        print("请确保:")
        print(f"  1. 运行: python ai_socket_server.py")
        print(f"  2. 防火墙允许端口 {SOCKET_PORT}")
        return False
    except Exception as e:
        print(f"[ERR] 检查服务器时出错: {str(e)}")
        return False

def main():
    """主函数"""
    print("="*70)
    print("MT5 AI交易系统 - Socket通信性能基准测试")
    print("="*70)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器地址: {SOCKET_HOST}:{SOCKET_PORT}")
    print(f"总请求数: {NUM_REQUESTS}")
    print(f"并发线程数: {CONCURRENT_REQUESTS}")
    print("-"*70)
    
    # 检查服务器可用性
    if not check_server_availability():
        return
    
    # 与文件模式对比
    compare_with_file_mode()
    
    print("\n" + "="*70)
    print("开始性能测试")
    print("="*70)
    
    # 运行顺序测试
    sequential_result = run_sequential_test(min(10, NUM_REQUESTS))
    print_test_result(sequential_result)
    
    # 运行并发测试
    if NUM_REQUESTS > 10:
        concurrent_result = run_concurrent_test(
            NUM_REQUESTS - 10, 
            CONCURRENT_REQUESTS
        )
        print_test_result(concurrent_result)
        
        # 合并结果
        total_result = TestResult("Socket综合测试")
        total_result.times = sequential_result.times + concurrent_result.times
        total_result.success_count = sequential_result.success_count + concurrent_result.success_count
        total_result.fail_count = sequential_result.fail_count + concurrent_result.fail_count
        total_result.errors = sequential_result.errors + concurrent_result.errors
        total_result.start_time = min(sequential_result.start_time, concurrent_result.start_time)
        total_result.end_time = max(sequential_result.end_time, concurrent_result.end_time)
        
        print("\n" + "="*70)
        print("综合测试结果")
        print("="*70)
        print_test_result(total_result)
        
        # 评估是否达到优化目标
        stats = total_result.get_stats()
        
        print("\n" + "="*70)
        print("优化目标达成评估")
        print("="*70)
        
        targets_met = 0
        total_targets = 4
        
        # 目标1: 平均响应时间 < 100ms
        avg_time_ms = stats['avg_time'] * 1000
        if avg_time_ms < 100:
            print(f"[OK] 目标1达成: 平均响应时间 {avg_time_ms:.1f}ms < 100ms")
            targets_met += 1
        else:
            print(f"[ERR] 目标1未达成: 平均响应时间 {avg_time_ms:.1f}ms >= 100ms")
        
        # 目标2: 成功率 > 99%
        success_rate = stats['success_rate']
        if success_rate > 99:
            print(f"[OK] 目标2达成: 成功率 {success_rate:.1f}% > 99%")
            targets_met += 1
        else:
            print(f"[ERR] 目标2未达成: 成功率 {success_rate:.1f}% <= 99%")
        
        # 目标3: 最大响应时间 < 1秒
        max_time_ms = stats['max_time'] * 1000
        if max_time_ms < 1000:
            print(f"[OK] 目标3达成: 最大响应时间 {max_time_ms:.1f}ms < 1000ms")
            targets_met += 1
        else:
            print(f"[ERR] 目标3未达成: 最大响应时间 {max_time_ms:.1f}ms >= 1000ms")
        
        # 目标4: 支持并发请求
        if CONCURRENT_REQUESTS > 1 and concurrent_result.success_count > 0:
            print(f"[OK] 目标4达成: 支持{CONCURRENT_REQUESTS}个并发请求")
            targets_met += 1
        else:
            print(f"[ERR] 目标4未达成: 并发处理能力不足")
        
        print(f"\n达成目标: {targets_met}/{total_targets}")
        
        if targets_met >= 3:
            print("\n[DONE] Socket通信方案技术可行性验证通过！")
            print("建议继续推进第2阶段集成开发。")
        else:
            print("\n[WARN]  Socket通信方案需要进一步优化。")
            print("建议检查服务器配置和网络设置。")
        
        print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n🛑 测试被用户中断")
    except Exception as e:
        print(f"\n[ERR] 测试运行出错: {str(e)}")
        import traceback
        traceback.print_exc()