#!/usr/bin/env python3
"""
加权速率限制器快速验证脚本
"""

import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.async_optimizer import EnhancedAsyncRateLimiter

async def test_weighted_rate_limiter():
    """测试加权速率限制器"""
    print("=" * 60)
    print("加权速率限制器快速验证")
    print("=" * 60)
    
    # 创建速率限制器
    rate_limiter = EnhancedAsyncRateLimiter(operations_per_second=10.0, burst_size=5, strict_mode=True)
    
    # 设置客户端权重
    rate_limiter.set_client_weight("client_high", 2.0)  # 高权重
    rate_limiter.set_client_weight("client_normal", 1.0)  # 正常权重
    rate_limiter.set_client_weight("client_low", 0.5)  # 低权重
    
    print("[INFO] 客户端权重设置:")
    print("  - client_high: 权重=2.0")
    print("  - client_normal: 权重=1.0")
    print("  - client_low: 权重=0.5")
    
    # 测试高权重客户端
    print("\n[TEST] 测试高权重客户端 (权重=2.0)")
    high_success_count = 0
    for i in range(5):
        success, wait_time = await rate_limiter.acquire(tokens=1, client_id="client_high")
        if success:
            high_success_count += 1
            print(f"  请求{i+1}: 成功 (等待: {wait_time:.3f}s)")
        else:
            print(f"  请求{i+1}: 受限 (需等待: {wait_time:.3f}s)")
            await asyncio.sleep(wait_time)
    
    # 重置令牌桶以便公平测试
    rate_limiter.tokens = 5.0
    rate_limiter.last_refill_time = time.monotonic_ns()
    
    # 测试正常权重客户端
    print("\n[TEST] 测试正常权重客户端 (权重=1.0)")
    normal_success_count = 0
    for i in range(5):
        success, wait_time = await rate_limiter.acquire(tokens=1, client_id="client_normal")
        if success:
            normal_success_count += 1
            print(f"  请求{i+1}: 成功 (等待: {wait_time:.3f}s)")
        else:
            print(f"  请求{i+1}: 受限 (需等待: {wait_time:.3f}s)")
            await asyncio.sleep(wait_time)
    
    # 重置令牌桶以便公平测试
    rate_limiter.tokens = 5.0
    rate_limiter.last_refill_time = time.monotonic_ns()
    
    # 测试低权重客户端
    print("\n[TEST] 测试低权重客户端 (权重=0.5)")
    low_success_count = 0
    for i in range(5):
        success, wait_time = await rate_limiter.acquire(tokens=1, client_id="client_low")
        if success:
            low_success_count += 1
            print(f"  请求{i+1}: 成功 (等待: {wait_time:.3f}s)")
        else:
            print(f"  请求{i+1}: 受限 (需等待: {wait_time:.3f}s)")
            await asyncio.sleep(wait_time)
    
    print("\n[RESULT] 成功率统计:")
    print(f"  高权重客户端: {high_success_count}/5 = {high_success_count/5*100:.1f}%")
    print(f"  正常权重客户端: {normal_success_count}/5 = {normal_success_count/5*100:.1f}%")
    print(f"  低权重客户端: {low_success_count}/5 = {low_success_count/5*100:.1f}%")
    
    # 验证权重机制
    print("\n[ANALYSIS] 权重机制验证:")
    if high_success_count >= normal_success_count >= low_success_count:
        print("  [PASS] 权重机制正常工作: 高权重 > 正常 > 低权重")
    else:
        print("  [FAIL] 权重机制异常")
    
    # 获取统计信息
    stats = rate_limiter.get_stats()
    print(f"\n[STATS] 速率限制器统计:")
    print(f"  目标速率: {stats['target_rate_per_second']:.1f} 次/秒")
    print(f"  实际速率: {stats['actual_rate_per_second']:.1f} 次/秒")
    print(f"  符合度: {stats['compliance_percent']:.1f}%")
    print(f"  总请求: {stats['total_requests']}")
    print(f"  允许请求: {stats['allowed_requests']}")
    print(f"  限制请求: {stats['rate_limited_requests']}")
    
    print("=" * 60)
    
    return {
        "high_success": high_success_count,
        "normal_success": normal_success_count,
        "low_success": low_success_count,
        "weights_working": high_success_count >= normal_success_count >= low_success_count
    }

async def test_concurrent_weighted():
    """测试并发加权场景"""
    print("\n" + "=" * 60)
    print("并发加权场景测试")
    print("=" * 60)
    
    rate_limiter = EnhancedAsyncRateLimiter(operations_per_second=20.0, burst_size=10, strict_mode=True)
    
    # 设置不同权重客户端
    clients = [
        ("client_A", 3.0),  # 最高优先级
        ("client_B", 2.0),  # 高优先级
        ("client_C", 1.0),  # 正常优先级
        ("client_D", 0.7),  # 低优先级
        ("client_E", 0.3),  # 最低优先级
    ]
    
    for client_id, weight in clients:
        rate_limiter.set_client_weight(client_id, weight)
    
    print("[INFO] 客户端配置:")
    for client_id, weight in clients:
        print(f"  - {client_id}: 权重={weight}")
    
    async def run_client(client_id, weight, requests=10):
        """单个客户端任务"""
        start_time = time.time()
        success_count = 0
        total_wait = 0
        
        for i in range(requests):
            success, wait_time = await rate_limiter.acquire(tokens=1, client_id=client_id)
            if success:
                success_count += 1
            else:
                total_wait += wait_time
                await asyncio.sleep(wait_time)
            
            # 添加微小随机间隔，模拟真实场景
            await asyncio.sleep(0.001)
        
        end_time = time.time()
        return {
            "client_id": client_id,
            "weight": weight,
            "total_time": end_time - start_time,
            "success_count": success_count,
            "success_rate": success_count / requests * 100,
            "total_wait": total_wait
        }
    
    # 并发运行所有客户端
    tasks = []
    for client_id, weight in clients:
        task = run_client(client_id, weight, 10)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    print("\n[RESULT] 并发加权测试结果:")
    for result in sorted(results, key=lambda x: x["weight"], reverse=True):
        print(f"  {result['client_id']} (权重={result['weight']}):")
        print(f"    成功率: {result['success_rate']:.1f}%")
        print(f"    总耗时: {result['total_time']:.3f}s")
        print(f"    等待时间: {result['total_wait']:.3f}s")
    
    # 分析权重效果
    print("\n[ANALYSIS] 权重效果验证:")
    weights = [r["weight"] for r in results]
    success_rates = [r["success_rate"] for r in results]
    
    # 检查权重与成功率是否正相关
    import statistics
    if len(success_rates) >= 2:
        correlation = statistics.correlation(weights, success_rates) if len(success_rates) >= 2 else 0
        if correlation > 0.7:
            print(f"  [PASS] 强正相关 (r={correlation:.3f}): 权重越高，成功率越高")
        elif correlation > 0.3:
            print(f"  [WARN] 中等正相关 (r={correlation:.3f}): 权重机制有效但可优化")
        else:
            print(f"  [FAIL] 弱相关 (r={correlation:.3f}): 权重机制效果不明显")
    
    print("=" * 60)
    
    return results

async def main():
    """主测试函数"""
    try:
        # 测试基本加权功能
        print("开始测试加权速率限制器...")
        result1 = await test_weighted_rate_limiter()
        
        # 等待一段时间重置令牌桶
        await asyncio.sleep(1)
        
        # 测试并发加权场景
        result2 = await test_concurrent_weighted()
        
        # 总体评估
        print("\n[SUMMARY] 加权速率限制器评估:")
        if result1["weights_working"]:
            print("  [PASS] 基本加权功能测试通过")
        else:
            print("  [FAIL] 基本加权功能测试失败")
        
        # 检查并发测试中的权重相关性
        weights = [r["weight"] for r in result2]
        success_rates = [r["success_rate"] for r in result2]
        if len(success_rates) >= 2:
            import statistics
            correlation = statistics.correlation(weights, success_rates) if len(success_rates) >= 2 else 0
            if correlation > 0.3:
                print(f"  [PASS] 并发加权测试通过 (相关性: {correlation:.3f})")
            else:
                print(f"  [WARN] 并发加权测试需要优化 (相关性: {correlation:.3f})")
        
        print("\n测试完成！")
        return True
        
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(main())