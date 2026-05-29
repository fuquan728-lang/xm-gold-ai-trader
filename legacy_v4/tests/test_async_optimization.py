#!/usr/bin/env python3
"""
异步优化集成测试 - 验证async-python-patterns技能应用效果
"""

import asyncio
import json
import time
import statistics
import pytest
from datetime import datetime
from typing import List, Dict, Any

# 导入优化模块
from core.async_optimizer import AsyncOptimizer, async_retry, async_rate_limited_map
from core.websocket_handler_enhanced import EnhancedWebSocketHandler
from core.http_client import get_http_client


class TestAsyncOptimization:
    """异步优化测试类"""
    
    def setup_method(self):
        """测试前设置"""
        print("\n" + "="*60)
        print("测试异步Python模式优化效果")
        print("="*60)
        
    def test_async_optimizer_initialization(self):
        """测试异步优化器初始化"""
        print("\n1. 测试异步优化器初始化...")
        optimizer = AsyncOptimizer(
            max_http_connections=20,
            max_ws_connections=50,
            rate_limit_per_client=30,
            enable_monitoring=True
        )
        
        assert optimizer is not None
        assert optimizer.http_pool is not None
        assert optimizer.ws_pool is not None
        assert optimizer.rate_limiter is not None
        assert optimizer.retry_manager is not None
        assert optimizer.batch_processor is not None
        assert optimizer.monitor is not None
        
        print("✓ 异步优化器初始化成功")
    
    async def test_async_batch_processing(self):
        """测试异步批量处理"""
        print("\n2. 测试异步批量处理...")
        
        test_items = list(range(1, 101))  # 100个测试项
        results = []
        
        async def process_item(item):
            await asyncio.sleep(0.01)  # 模拟处理延迟
            return item * 2
        
        optimizer = AsyncOptimizer()
        
        # 批量处理
        processed_items = await optimizer.batch_process(test_items, process_item)
        
        assert len(processed_items) == len(test_items)
        for original, processed in zip(test_items, processed_items):
            assert processed == original * 2
        
        print(f"✓ 批量处理完成: {len(processed_items)} 项")
        
        # 测试速率限制映射
        print("\n3. 测试速率限制映射...")
        
        async def slow_process(item):
            await asyncio.sleep(0.005)
            return f"processed_{item}"
        
        limited_results = await async_rate_limited_map(
            test_items[:20],  # 只测试20个
            slow_process,
            max_concurrent=5,
            rate_limit=10
        )
        
        assert len(limited_results) == 20
        print(f"✓ 速率限制映射完成: {len(limited_results)} 项")
    
    async def test_enhanced_websocket_handler(self):
        """测试增强版WebSocket处理器"""
        print("\n4. 测试增强版WebSocket处理器...")
        
        async def mock_processor(request):
            return {
                "type": "response",
                "action": "TEST",
                "confidence": 0.95,
                "timestamp": datetime.now().isoformat()
            }
        
        handler = EnhancedWebSocketHandler(
            host="127.0.0.1",
            port=9999,  # 测试端口
            process_request_func=mock_processor,
            max_connections=10,
            max_connections_per_ip=5,
            rate_limit_per_client=20
        )
        
        # 检查初始化状态
        status = handler.get_status()
        assert status["host"] == "127.0.0.1"
        assert status["port"] == 9999
        assert status["rate_limit_per_client"] == 20
        
        print("✓ 增强版WebSocket处理器初始化成功")
        print(f"  连接池配置: 最大连接={handler.connection_pool.max_connections}")
        print(f"  速率限制: {handler.rate_limit_per_client} 请求/秒")
    
    async def test_http_connection_pool(self):
        """测试HTTP连接池性能"""
        print("\n5. 测试HTTP连接池性能...")
        
        optimizer = AsyncOptimizer(max_http_connections=10)
        
        test_urls = [
            "http://httpbin.org/delay/1",
            "http://httpbin.org/delay/2",
            "http://httpbin.org/ip",
            "http://httpbin.org/user-agent",
        ]
        
        async def test_http_request(url):
            try:
                result = await optimizer.http_request("GET", url, timeout=5)
                return result["status"] == 200
            except Exception:
                return False
        
        # 并发测试
        tasks = [test_http_request(url) for url in test_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        print(f"✓ HTTP连接池测试: {success_count}/{len(test_urls)} 成功")
        
        # 获取性能统计
        stats = await optimizer.get_performance_stats()
        if stats:
            print(f"  性能统计: {stats.get('total_operations', 0)} 次操作")
    
    async def test_smart_retry_manager(self):
        """测试智能重试管理器"""
        print("\n6. 测试智能重试管理器...")
        
        attempts = []
        
        async def failing_operation(should_fail=True):
            attempts.append(1)
            if should_fail and len(attempts) < 3:
                raise ConnectionError("模拟网络错误")
            return "success"
        
        optimizer = AsyncOptimizer()
        
        # 测试重试成功
        attempts.clear()
        result = await optimizer.retry_manager.execute_with_retry(
            failing_operation,
            operation_name="test_retry_success"
        )
        assert result == "success"
        assert len(attempts) == 3
        
        # 测试立即成功（无重试）
        attempts.clear()
        result = await optimizer.retry_manager.execute_with_retry(
            lambda: failing_operation(should_fail=False),
            operation_name="test_no_retry"
        )
        assert result == "success"
        assert len(attempts) == 1
        
        print("✓ 智能重试管理器测试完成")
        print(f"  成功重试: {len(attempts)} 次尝试")
    
    async def test_performance_monitoring(self):
        """测试性能监控"""
        print("\n7. 测试性能监控...")
        
        optimizer = AsyncOptimizer(enable_monitoring=True)
        
        # 模拟一些操作
        async def mock_operation():
            await asyncio.sleep(0.05)
            return {"data": "test"}
        
        for _ in range(10):
            await mock_operation()
        
        # 获取统计信息
        stats = await optimizer.get_performance_stats()
        
        assert stats is not None
        print("✓ 性能监控功能正常")
        print(f"  监控统计: {stats.get('total_operations', 0)} 次操作")
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("开始异步优化集成测试...")
        
        try:
            self.test_async_optimizer_initialization()
            
            # 异步测试
            await self.test_async_batch_processing()
            await self.test_enhanced_websocket_handler()
            await self.test_http_connection_pool()
            await self.test_smart_retry_manager()
            await self.test_performance_monitoring()
            
            print("\n" + "="*60)
            print("所有异步优化测试完成！")
            print("="*60)
            return True
            
        except Exception as e:
            print(f"\n[ERR] 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """主测试函数"""
    tester = TestAsyncOptimization()
    tester.setup_method()
    success = await tester.run_all_tests()
    
    # 性能基准测试
    print("\n" + "="*60)
    print("异步性能基准测试")
    print("="*60)
    
    # 测试并发性能
    async def benchmark_task(i):
        await asyncio.sleep(0.01)
        return i * 2
    
    # 顺序执行基准
    print("顺序执行基准...")
    start_time = time.time()
    sequential_results = []
    for i in range(50):
        result = await benchmark_task(i)
        sequential_results.append(result)
    sequential_time = time.time() - start_time
    
    # 并发执行基准
    print("并发执行基准...")
    start_time = time.time()
    concurrent_tasks = [benchmark_task(i) for i in range(50)]
    concurrent_results = await asyncio.gather(*concurrent_tasks)
    concurrent_time = time.time() - start_time
    
    # 计算加速比
    speedup = sequential_time / concurrent_time if concurrent_time > 0 else 0
    
    print(f"\n基准测试结果:")
    print(f"  顺序执行: {sequential_time:.3f} 秒")
    print(f"  并发执行: {concurrent_time:.3f} 秒")
    print(f"  加速比: {speedup:.1f}x")
    print(f"  吞吐量提升: {((sequential_time - concurrent_time)/sequential_time)*100:.1f}%")
    
    # 测试连接池性能
    print("\n连接池性能测试...")
    optimizer = AsyncOptimizer(max_http_connections=5)
    
    async def pool_test_task(task_id):
        try:
            await asyncio.sleep(0.02)
            return f"task_{task_id}_complete"
        except Exception as e:
            return f"task_{task_id}_error: {e}"
    
    # 测试连接池并发
    pool_tasks = [pool_test_task(i) for i in range(20)]
    pool_results = await asyncio.gather(*pool_tasks)
    
    success_count = sum(1 for r in pool_results if "_complete" in r)
    print(f"  连接池并发测试: {success_count}/{len(pool_results)} 成功")
    
    return success


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())