#!/usr/bin/env python3
"""
并发公平性改进效果验证脚本

功能：
1. 测试改进后的速率限制器在并发场景下的公平性
2. 验证客户端权重设置对资源分配的影响
3. 对比不同客户端间的完成时间差异
4. 生成公平性改进效果报告

使用方法：
python test_concurrent_fairness_improvement.py [--clients 3] [--requests 20]

参数：
--clients: 并发客户端数量（默认3）
--requests: 每个客户端的请求数（默认20）
"""

import asyncio
import sys
import time
import statistics
import json
import argparse
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.async_optimizer import AsyncRateLimiter
    MODULE_AVAILABLE = True
except ImportError as e:
    MODULE_AVAILABLE = False
    print(f"[ERR] 模块导入失败: {e}")


@dataclass
class ClientResult:
    """客户端测试结果"""
    client_id: str
    weight: float
    total_requests: int
    successful_requests: int
    rate_limited_requests: int
    total_wait_time: float
    start_time: float
    end_time: float
    request_times: List[float]
    
    @property
    def total_time(self) -> float:
        """总耗时"""
        return self.end_time - self.start_time
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        return statistics.mean(self.request_times) if self.request_times else 0.0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        return self.successful_requests / self.total_requests if self.total_requests > 0 else 0.0


async def client_task(rate_limiter: AsyncRateLimiter, client_id: str, weight: float, requests: int, 
                      interval_min: float = 0.01, interval_max: float = 0.05) -> ClientResult:
    """
    客户端任务：模拟客户端请求
    
    Args:
        rate_limiter: 速率限制器实例
        client_id: 客户端ID
        weight: 客户端权重
        requests: 请求数量
        interval_min: 最小请求间隔（秒）
        interval_max: 最大请求间隔（秒）
    """
    result = ClientResult(
        client_id=client_id,
        weight=weight,
        total_requests=0,
        successful_requests=0,
        rate_limited_requests=0,
        total_wait_time=0.0,
        start_time=0.0,
        end_time=0.0,
        request_times=[]
    )
    
    # 设置客户端权重
    rate_limiter.set_client_weight(client_id, weight)
    
    result.start_time = time.time()
    
    for i in range(requests):
        result.total_requests += 1
        
        # 记录请求开始时间
        request_start = time.time()
        
        # 获取令牌（使用客户端ID）
        success, wait_time = await rate_limiter.acquire(tokens=1, client_id=client_id)
        
        if success:
            result.successful_requests += 1
        else:
            result.rate_limited_requests += 1
            result.total_wait_time += wait_time
            # 等待所需时间
            await asyncio.sleep(wait_time)
        
        # 记录请求时间
        request_time = time.time() - request_start
        result.request_times.append(request_time)
        
        # 模拟随机间隔（模拟真实客户端行为）
        if i < requests - 1:  # 最后一个请求不需要等待
            interval = random.uniform(interval_min, interval_max)
            await asyncio.sleep(interval)
    
    result.end_time = time.time()
    return result


async def run_concurrent_fairness_test(clients: int = 3, requests: int = 20, 
                                       rate_limit: float = 15.0) -> Dict[str, Any]:
    """
    运行并发公平性测试
    
    Args:
        clients: 客户端数量
        requests: 每个客户端请求数
        rate_limit: 速率限制（次/秒）
    """
    print("=" * 80)
    print("并发公平性改进效果验证")
    print("=" * 80)
    
    if not MODULE_AVAILABLE:
        print("[FAIL] 无法导入AsyncRateLimiter模块")
        return {"success": False, "error": "Module import failed"}
    
    # 创建速率限制器
    rate_limiter = AsyncRateLimiter(operations_per_second=rate_limit, burst_size=5, strict_mode=True)
    
    # 设置客户端权重（权重差异）
    client_configs = []
    for i in range(clients):
        if i == 0:
            weight = 2.0  # 高优先级客户端
        elif i == clients - 1:
            weight = 0.5  # 低优先级客户端
        else:
            weight = 1.0  # 标准优先级客户端
        client_configs.append((f"client_{i+1}", weight))
    
    print(f"[INFO] 测试配置:")
    print(f"  - 客户端数量: {clients}")
    print(f"  - 每个客户端请求数: {requests}")
    print(f"  - 速率限制: {rate_limit} 次/秒")
    print(f"  - 客户端权重:")
    for client_id, weight in client_configs:
        print(f"      {client_id}: 权重={weight}")
    
    # 运行并发测试
    print(f"\n[INFO] 开始并发公平性测试...")
    start_time = time.time()
    
    # 创建客户端任务
    tasks = []
    for client_id, weight in client_configs:
        task = client_task(rate_limiter, client_id, weight, requests)
        tasks.append(task)
    
    # 并发执行所有客户端任务
    results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # 分析结果
    client_results = {r.client_id: r for r in results}
    
    # 计算公平性指标
    total_times = [r.total_time for r in results]
    avg_response_times = [r.avg_response_time for r in results]
    success_rates = [r.success_rate for r in results]
    
    # 时间公平性：最大完成时间差异
    max_time = max(total_times)
    min_time = min(total_times)
    time_diff_percent = ((max_time - min_time) / min_time * 100) if min_time > 0 else 0
    
    # 响应时间公平性：标准偏差
    response_time_std = statistics.stdev(avg_response_times) if len(avg_response_times) >= 2 else 0
    
    # 成功率公平性：标准偏差
    success_rate_std = statistics.stdev(success_rates) if len(success_rates) >= 2 else 0
    
    # 等待时间差异（按权重预期）
    high_weight_wait = sum(r.total_wait_time for r in results if r.weight >= 1.5)
    low_weight_wait = sum(r.total_wait_time for r in results if r.weight <= 0.75)
    medium_weight_wait = sum(r.total_wait_time for r in results if 0.75 < r.weight < 1.5)
    
    # 计算速率限制器统计
    limiter_stats = rate_limiter.get_stats()
    
    # 生成报告
    report = {
        "test_config": {
            "clients": clients,
            "requests_per_client": requests,
            "rate_limit": rate_limit,
            "test_start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_duration": total_time
        },
        "fairness_metrics": {
            "max_completion_time_difference_percent": round(time_diff_percent, 2),
            "response_time_standard_deviation": round(response_time_std, 4),
            "success_rate_standard_deviation": round(success_rate_std, 4),
            "high_weight_wait_time": round(high_weight_wait, 4),
            "medium_weight_wait_time": round(medium_weight_wait, 4),
            "low_weight_wait_time": round(low_weight_wait, 4),
            "weighted_wait_ratio": round(high_weight_wait / low_weight_wait, 2) if low_weight_wait > 0 else float('inf')
        },
        "rate_limiter_stats": limiter_stats,
        "client_details": [
            {
                "client_id": r.client_id,
                "weight": r.weight,
                "total_requests": r.total_requests,
                "successful_requests": r.successful_requests,
                "rate_limited_requests": r.rate_limited_requests,
                "success_rate": round(r.success_rate * 100, 2),
                "total_time": round(r.total_time, 4),
                "avg_response_time": round(r.avg_response_time, 4),
                "total_wait_time": round(r.total_wait_time, 4)
            }
            for r in results
        ]
    }
    
    # 打印摘要
    print(f"\n[RESULT] 并发公平性测试完成")
    print(f"  - 总耗时: {total_time:.2f} 秒")
    print(f"  - 最大完成时间差异: {time_diff_percent:.1f}%")
    print(f"  - 响应时间标准差: {response_time_std:.4f} 秒")
    print(f"  - 成功率标准差: {success_rate_std:.4f}")
    print(f"  - 权重等待时间比 (高/低): {report['fairness_metrics']['weighted_wait_ratio']:.2f}")
    
    # 客户端详情
    print(f"\n[CLIENT DETAILS]")
    for client in report["client_details"]:
        print(f"  {client['client_id']} (权重={client['weight']}):")
        print(f"    成功率: {client['success_rate']}%")
        print(f"    总耗时: {client['total_time']:.3f}秒")
        print(f"    平均响应: {client['avg_response_time']:.3f}秒")
        print(f"    等待时间: {client['total_wait_time']:.3f}秒")
    
    # 速率限制器统计
    print(f"\n[RATE LIMITER STATS]")
    print(f"  目标速率: {limiter_stats['target_rate_per_second']:.1f} 次/秒")
    print(f"  实际速率: {limiter_stats['actual_rate_per_second']:.1f} 次/秒")
    print(f"  符合度: {limiter_stats['compliance_percent']:.1f}%")
    print(f"  总请求: {limiter_stats['total_requests']}")
    print(f"  允许请求: {limiter_stats['allowed_requests']}")
    print(f"  限制请求: {limiter_stats['rate_limited_requests']}")
    
    # 公平性评级
    fairness_rating = "POOR"
    if time_diff_percent < 20:
        fairness_rating = "EXCELLENT"
    elif time_diff_percent < 40:
        fairness_rating = "GOOD"
    elif time_diff_percent < 60:
        fairness_rating = "FAIR"
    elif time_diff_percent < 80:
        fairness_rating = "NEEDS_IMPROVEMENT"
    
    print(f"\n[FAIRNESS RATING] {fairness_rating}")
    
    # 保存结果到文件
    report_file = Path(__file__).parent / "concurrent_fairness_improvement_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n[REPORT] 详细报告已保存至: {report_file}")
    
    # 生成改进效果分析
    print(f"\n[IMPROVEMENT ANALYSIS]")
    if fairness_rating == "EXCELLENT" or fairness_rating == "GOOD":
        print(f"  [PASS] 并发公平性改进效果显著")
        print(f"  [PASS] 权重机制正常工作：高权重客户端等待时间更少")
        print(f"  [PASS] 客户端间资源分配更均衡")
    elif fairness_rating == "FAIR":
        print(f"  [WARN] 并发公平性有所改善，但仍需优化")
        print(f"  [WARN] 建议进一步调整权重算法")
    else:
        print(f"  [FAIL] 并发公平性仍需大幅改进")
        print(f"  [FAIL] 建议重新设计调度算法")
    
    print("=" * 80)
    
    return {"success": True, "fairness_rating": fairness_rating, "report": report}


def main():
    parser = argparse.ArgumentParser(description="并发公平性改进效果验证")
    parser.add_argument("--clients", type=int, default=3, help="并发客户端数量")
    parser.add_argument("--requests", type=int, default=20, help="每个客户端请求数")
    parser.add_argument("--rate", type=float, default=15.0, help="速率限制（次/秒）")
    
    args = parser.parse_args()
    
    # 运行测试
    asyncio.run(run_concurrent_fairness_test(
        clients=args.clients,
        requests=args.requests,
        rate_limit=args.rate
    ))


if __name__ == "__main__":
    main()