#!/usr/bin/env python3
"""
科学智能交易系统 - 系统优化器
确保高并发、低延迟和可扩展性
"""

import asyncio
import threading
import multiprocessing
import queue
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import heapq
import uuid

from core.logger import logger


class ConcurrencyMode(Enum):
    """并发模式"""
    SYNC = "sync"          # 同步模式
    THREAD = "thread"      # 多线程模式
    ASYNC = "async"        # 异步模式
    PROCESS = "process"    # 多进程模式


class CacheStrategy(Enum):
    """缓存策略"""
    LRU = "lru"            # 最近最少使用
    LFU = "lfu"            # 最不经常使用
    FIFO = "fifo"          # 先进先出
    MRU = "mru"            # 最近最多使用
    TTL = "ttl"            # 生存时间


@dataclass
class PerformanceMetrics:
    """性能指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    throughput: float = 0.0
    error_rate: float = 0.0
    cache_hit_rate: float = 0.0
    concurrent_connections: int = 0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0


class PriorityTask:
    """优先级任务"""
    
    def __init__(self, priority: int, task_id: str, func: Callable, *args, **kwargs):
        self.priority = priority  # 数值越小优先级越高
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.created_time = time.time()
        self.result = None
        self.exception = None
    
    def __lt__(self, other):
        # 优先级比较：优先处理高优先级（数值小）的任务
        if self.priority == other.priority:
            return self.created_time < other.created_time
        return self.priority < other.priority
    
    def execute(self):
        """执行任务"""
        try:
            self.result = self.func(*self.args, **self.kwargs)
            return self.result
        except Exception as e:
            self.exception = e
            raise


class LRUCache:
    """LRU缓存"""
    
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.cache: Dict[str, Any] = {}
        self.order: List[str] = []
        self.hits = 0
        self.misses = 0
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key in self.cache:
                # 更新访问顺序
                self.order.remove(key)
                self.order.append(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1
            return None
    
    def put(self, key: str, value: Any):
        """设置缓存值"""
        with self.lock:
            if key in self.cache:
                # 更新现有值
                self.cache[key] = value
                self.order.remove(key)
                self.order.append(key)
            else:
                # 新增值
                if len(self.cache) >= self.capacity:
                    # 移除最久未使用的
                    oldest = self.order.pop(0)
                    del self.cache[oldest]
                self.cache[key] = value
                self.order.append(key)
    
    def invalidate(self, key: str):
        """使缓存失效"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                if key in self.order:
                    self.order.remove(key)
    
    def clear(self):
        """清空缓存"""
        with self.lock:
            self.cache.clear()
            self.order.clear()
    
    def get_hit_rate(self) -> float:
        """获取缓存命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def size(self) -> int:
        """获取缓存大小"""
        return len(self.cache)


class ConnectionPool:
    """连接池"""
    
    def __init__(self, max_connections: int = 100, idle_timeout: int = 300):
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout
        self.active_connections: Dict[str, Any] = {}
        self.idle_connections: List[tuple] = []  # (last_used_time, connection)
        self.waiting_requests: queue.Queue = queue.Queue()
        self.lock = threading.RLock()
        
        # 清理线程
        self.cleanup_thread = threading.Thread(target=self._cleanup_idle_connections, daemon=True)
        self.cleanup_thread.start()
        
        logger.info(f"[REFRESH] 连接池初始化完成: 最大连接数={max_connections}, 空闲超时={idle_timeout}s")
    
    def acquire(self, connection_id: str, creator: Callable) -> Any:
        """获取连接"""
        with self.lock:
            # 检查是否已有连接
            if connection_id in self.active_connections:
                return self.active_connections[connection_id]
            
            # 检查空闲连接
            for i, (last_used, conn) in enumerate(self.idle_connections):
                if last_used + self.idle_timeout < time.time():
                    # 连接已超时，清理
                    self.idle_connections.pop(i)
                    continue
                
                # 使用空闲连接
                self.idle_connections.pop(i)
                self.active_connections[connection_id] = conn
                return conn
            
            # 创建新连接
            if len(self.active_connections) + len(self.idle_connections) < self.max_connections:
                conn = creator()
                self.active_connections[connection_id] = conn
                return conn
            
            # 等待可用连接
            logger.warning(f"[WARN]  连接池已满，等待可用连接...")
            return None
    
    def release(self, connection_id: str):
        """释放连接"""
        with self.lock:
            if connection_id in self.active_connections:
                conn = self.active_connections.pop(connection_id)
                self.idle_connections.append((time.time(), conn))
    
    def _cleanup_idle_connections(self):
        """清理空闲连接"""
        while True:
            try:
                with self.lock:
                    current_time = time.time()
                    self.idle_connections = [
                        (last_used, conn)
                        for last_used, conn in self.idle_connections
                        if current_time - last_used < self.idle_timeout
                    ]
                
                time.sleep(60)  # 每分钟清理一次
                
            except Exception as e:
                logger.error(f"[ERR] 清理空闲连接失败: {e}")
                time.sleep(300)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self.lock:
            return {
                "active_connections": len(self.active_connections),
                "idle_connections": len(self.idle_connections),
                "total_connections": len(self.active_connections) + len(self.idle_connections),
                "max_connections": self.max_connections,
                "waiting_requests": self.waiting_requests.qsize()
            }


class TaskScheduler:
    """任务调度器"""
    
    def __init__(self, max_workers: int = 10, mode: ConcurrencyMode = ConcurrencyMode.THREAD):
        self.max_workers = max_workers
        self.mode = mode
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.running_tasks: Dict[str, Any] = {}
        self.completed_tasks: Dict[str, Any] = {}
        self.executor = None
        self.loop = None
        self.running = False
        self.worker_threads: List[threading.Thread] = []
        
        self._init_executor()
        logger.info(f"-> 任务调度器初始化完成: 模式={mode.value}, 最大工作线程={max_workers}")
    
    def _init_executor(self):
        """初始化执行器"""
        if self.mode == ConcurrencyMode.THREAD:
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        elif self.mode == ConcurrencyMode.PROCESS:
            self.executor = ProcessPoolExecutor(max_workers=self.max_workers)
        elif self.mode == ConcurrencyMode.ASYNC:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
    
    def start(self):
        """启动调度器"""
        if self.running:
            logger.warning("[WARN]  任务调度器已在运行中")
            return
        
        self.running = True
        
        # 启动工作线程
        for i in range(self.max_workers):
            thread = threading.Thread(target=self._worker_loop, daemon=True)
            thread.start()
            self.worker_threads.append(thread)
        
        logger.info("-> 任务调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self.running = False
        
        # 等待所有工作线程结束
        for thread in self.worker_threads:
            thread.join(timeout=5)
        
        if self.executor:
            self.executor.shutdown(wait=True)
        
        if self.loop and self.loop.is_running():
            self.loop.stop()
        
        logger.info("🛑 任务调度器已停止")
    
    def _worker_loop(self):
        """工作线程循环"""
        while self.running:
            try:
                # 获取任务
                task = self.task_queue.get(timeout=1)
                if task is None:
                    continue
                
                task_id = task.task_id
                self.running_tasks[task_id] = task
                
                try:
                    # 执行任务
                    result = task.execute()
                    
                    # 记录完成的任务
                    self.completed_tasks[task_id] = {
                        "result": result,
                        "completed_time": time.time(),
                        "duration": time.time() - task.created_time
                    }
                    
                    logger.debug(f"[OK] 任务执行完成: {task_id}, 耗时: {time.time() - task.created_time:.3f}s")
                    
                except Exception as e:
                    logger.error(f"[ERR] 任务执行失败: {task_id}, 错误: {e}")
                    self.completed_tasks[task_id] = {
                        "exception": str(e),
                        "completed_time": time.time(),
                        "duration": time.time() - task.created_time
                    }
                
                finally:
                    # 从运行任务中移除
                    if task_id in self.running_tasks:
                        del self.running_tasks[task_id]
                    
                    self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"[ERR] 工作线程异常: {e}")
                time.sleep(1)
    
    def submit(self, func: Callable, *args, priority: int = 5, **kwargs) -> str:
        """提交任务"""
        task_id = str(uuid.uuid4())
        task = PriorityTask(priority, task_id, func, *args, **kwargs)
        
        self.task_queue.put(task)
        logger.debug(f"📥 任务已提交: {task_id}, 优先级: {priority}")
        
        return task_id
    
    def submit_async(self, func: Callable, *args, **kwargs):
        """提交异步任务"""
        if self.mode != ConcurrencyMode.ASYNC:
            logger.warning("[WARN]  异步模式未启用，使用同步提交")
            return self.submit(func, *args, **kwargs)
        
        if not self.loop or not self.loop.is_running():
            logger.error("[ERR] 事件循环未运行")
            return None
        
        # 在事件循环中运行
        return asyncio.run_coroutine_threadsafe(func(*args, **kwargs), self.loop)
    
    def wait_for_completion(self, task_id: str, timeout: float = 30.0) -> Any:
        """等待任务完成"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if task_id in self.completed_tasks:
                task_result = self.completed_tasks[task_id]
                if "exception" in task_result:
                    raise Exception(f"任务执行失败: {task_result['exception']}")
                return task_result["result"]
            
            time.sleep(0.1)
        
        raise TimeoutError(f"等待任务超时: {task_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        return {
            "mode": self.mode.value,
            "max_workers": self.max_workers,
            "queue_size": self.task_queue.qsize(),
            "running_tasks": len(self.running_tasks),
            "completed_tasks": len(self.completed_tasks),
            "worker_threads": len(self.worker_threads)
        }


class SystemOptimizer:
    """系统优化器"""
    
    def __init__(self):
        # 缓存
        self.cache = LRUCache(capacity=5000)
        
        # 连接池
        self.db_connection_pool = ConnectionPool(max_connections=50, idle_timeout=300)
        self.api_connection_pool = ConnectionPool(max_connections=100, idle_timeout=180)
        
        # 任务调度器
        self.task_scheduler = TaskScheduler(max_workers=20, mode=ConcurrencyMode.THREAD)
        
        # 性能监控
        self.metrics = PerformanceMetrics()
        self.metrics_history: List[PerformanceMetrics] = []
        
        # 配置
        self.config = {
            "cache_enabled": True,
            "connection_pooling": True,
            "async_processing": True,
            "compression_enabled": True,
            "batch_processing": True,
            "monitoring_enabled": True
        }
        
        # 运行状态
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        logger.info("-> 系统优化器初始化完成")
    
    def start(self):
        """启动系统优化器"""
        if self.running:
            logger.warning("[WARN]  系统优化器已在运行中")
            return
        
        # 启动任务调度器
        self.task_scheduler.start()
        
        # 启动性能监控
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("-> 系统优化器已启动")
    
    def stop(self):
        """停止系统优化器"""
        self.running = False
        
        # 停止任务调度器
        self.task_scheduler.stop()
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("🛑 系统优化器已停止")
    
    def _monitor_loop(self):
        """性能监控循环"""
        logger.info("[REFRESH] 性能监控循环开始")
        
        while self.running:
            try:
                # 收集性能指标
                self._collect_metrics()
                
                # 检查系统健康状态
                self._check_system_health()
                
                # 自动调整配置
                self._auto_tune_config()
                
                time.sleep(60)  # 每分钟收集一次
                
            except Exception as e:
                logger.error(f"[ERR] 性能监控异常: {e}")
                time.sleep(300)
    
    def _collect_metrics(self):
        """收集性能指标"""
        try:
            # 获取缓存命中率
            cache_hit_rate = self.cache.get_hit_rate()
            
            # 获取连接池统计
            db_stats = self.db_connection_pool.get_stats()
            api_stats = self.api_connection_pool.get_stats()
            
            # 获取任务调度器统计
            scheduler_stats = self.task_scheduler.get_stats()
            
            # 更新性能指标
            self.metrics.cache_hit_rate = cache_hit_rate
            self.metrics.concurrent_connections = (
                db_stats["active_connections"] + api_stats["active_connections"]
            )
            
            # 记录历史指标
            self.metrics_history.append(self.metrics)
            if len(self.metrics_history) > 1440:  # 保留24小时数据（每分钟一次）
                self.metrics_history = self.metrics_history[-1440:]
            
            logger.debug(f"[DATA] 性能指标收集完成: 缓存命中率={cache_hit_rate:.2%}, "
                        f"并发连接数={self.metrics.concurrent_connections}")
            
        except Exception as e:
            logger.error(f"[ERR] 收集性能指标失败: {e}")
    
    def _check_system_health(self):
        """检查系统健康状态"""
        try:
            # 检查缓存命中率
            if self.metrics.cache_hit_rate < 0.3:
                logger.warning(f"[WARN]  缓存命中率较低: {self.metrics.cache_hit_rate:.2%}")
            
            # 检查连接池使用率
            db_stats = self.db_connection_pool.get_stats()
            db_usage = db_stats["total_connections"] / db_stats["max_connections"]
            
            if db_usage > 0.8:
                logger.warning(f"[WARN]  数据库连接池使用率较高: {db_usage:.1%}")
            
            # 检查任务队列
            scheduler_stats = self.task_scheduler.get_stats()
            if scheduler_stats["queue_size"] > 100:
                logger.warning(f"[WARN]  任务队列积压: {scheduler_stats['queue_size']}个任务")
            
        except Exception as e:
            logger.error(f"[ERR] 检查系统健康状态失败: {e}")
    
    def _auto_tune_config(self):
        """自动调整配置"""
        try:
            # 基于性能指标动态调整配置
            
            # 如果缓存命中率低，增加缓存容量
            if self.metrics.cache_hit_rate < 0.2:
                new_capacity = min(self.cache.capacity * 2, 10000)
                if new_capacity > self.cache.capacity:
                    logger.info(f"[REFRESH] 增加缓存容量: {self.cache.capacity} -> {new_capacity}")
                    # 这里可以实际调整缓存容量
            
            # 如果连接池使用率高，增加连接数
            db_stats = self.db_connection_pool.get_stats()
            db_usage = db_stats["total_connections"] / db_stats["max_connections"]
            
            if db_usage > 0.9:
                logger.info("[REFRESH] 数据库连接池使用率过高，考虑增加连接数")
            
        except Exception as e:
            logger.error(f"[ERR] 自动调整配置失败: {e}")
    
    def get_cached_data(self, key: str, fetcher: Callable, ttl: int = 300) -> Any:
        """获取缓存数据（如果缓存不存在则获取）"""
        if not self.config["cache_enabled"]:
            return fetcher()
        
        # 检查缓存
        cached_data = self.cache.get(key)
        if cached_data is not None:
            return cached_data
        
        # 缓存未命中，获取数据
        data = fetcher()
        
        # 缓存数据
        self.cache.put(key, data)
        
        return data
    
    def execute_with_retry(self, func: Callable, max_retries: int = 3, 
                          retry_delay: float = 1.0, *args, **kwargs) -> Any:
        """带重试的执行"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                logger.warning(f"[WARN]  执行失败，尝试 {attempt + 1}/{max_retries}: {e}")
                
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # 指数退避
        
        logger.error(f"[ERR] 执行失败，已达到最大重试次数: {last_exception}")
        raise last_exception
    
    def batch_process(self, items: List[Any], processor: Callable, 
                     batch_size: int = 100, parallel: bool = True) -> List[Any]:
        """批量处理"""
        if not self.config["batch_processing"]:
            return [processor(item) for item in items]
        
        results = []
        
        if parallel:
            # 并行处理
            task_ids = []
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                task_id = self.task_scheduler.submit(
                    lambda b: [processor(item) for item in b],
                    batch,
                    priority=3
                )
                task_ids.append(task_id)
            
            # 等待所有任务完成
            for task_id in task_ids:
                try:
                    batch_result = self.task_scheduler.wait_for_completion(task_id)
                    results.extend(batch_result)
                except Exception as e:
                    logger.error(f"[ERR] 批量处理任务失败: {task_id}, 错误: {e}")
        else:
            # 串行处理
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                batch_result = [processor(item) for item in batch]
                results.extend(batch_result)
        
        return results
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告"""
        return {
            "optimizer": {
                "cache_enabled": self.config["cache_enabled"],
                "connection_pooling": self.config["connection_pooling"],
                "async_processing": self.config["async_processing"],
                "compression_enabled": self.config["compression_enabled"],
                "batch_processing": self.config["batch_processing"]
            },
            "cache": {
                "hit_rate": self.cache.get_hit_rate(),
                "size": self.cache.size(),
                "capacity": self.cache.capacity
            },
            "connection_pools": {
                "database": self.db_connection_pool.get_stats(),
                "api": self.api_connection_pool.get_stats()
            },
            "task_scheduler": self.task_scheduler.get_stats(),
            "performance_metrics": {
                "cache_hit_rate": self.metrics.cache_hit_rate,
                "concurrent_connections": self.metrics.concurrent_connections,
                "total_requests": self.metrics.total_requests,
                "avg_response_time": self.metrics.avg_response_time,
                "error_rate": self.metrics.error_rate
            },
            "timestamp": time.time()
        }


# 全局系统优化器实例
_global_system_optimizer: Optional[SystemOptimizer] = None


def get_system_optimizer() -> SystemOptimizer:
    """获取全局系统优化器实例"""
    global _global_system_optimizer
    if not _global_system_optimizer:
        _global_system_optimizer = SystemOptimizer()
    return _global_system_optimizer


if __name__ == "__main__":
    # 测试系统优化器
    print("="*70)
    print("[TOOL] 测试系统优化器 - 高并发、低延迟、可扩展性")
    print("="*70)
    
    optimizer = SystemOptimizer()
    
    # 启动优化器
    optimizer.start()
    
    # 等待初始化
    time.sleep(1)
    
    # 测试缓存
    print("\n[REFRESH] 测试缓存功能...")
    
    def fetch_data(key):
        time.sleep(0.1)  # 模拟耗时操作
        return f"data_for_{key}"
    
    # 第一次获取（缓存未命中）
    start_time = time.time()
    data1 = optimizer.get_cached_data("test_key", lambda: fetch_data("test_key"))
    duration1 = time.time() - start_time
    print(f"   第一次获取: {data1}, 耗时: {duration1:.3f}s")
    
    # 第二次获取（缓存命中）
    start_time = time.time()
    data2 = optimizer.get_cached_data("test_key", lambda: fetch_data("test_key"))
    duration2 = time.time() - start_time
    print(f"   第二次获取: {data2}, 耗时: {duration2:.3f}s")
    
    # 测试批量处理
    print("\n[REFRESH] 测试批量处理...")
    
    def process_item(item):
        time.sleep(0.01)  # 模拟处理时间
        return item * 2
    
    items = list(range(1000))
    
    start_time = time.time()
    results = optimizer.batch_process(items, process_item, batch_size=100, parallel=True)
    duration = time.time() - start_time
    
    print(f"   批量处理 {len(items)} 个项目, 耗时: {duration:.3f}s")
    print(f"   前5个结果: {results[:5]}")
    
    # 测试重试机制
    print("\n[REFRESH] 测试重试机制...")
    
    attempt_count = [0]  # 使用列表以便在嵌套函数中修改
    
    def unreliable_function():
        attempt_count[0] += 1
        if attempt_count[0] < 3:
            raise Exception(f"模拟失败 (尝试 {attempt_count[0]})")
        return "成功"
    
    try:
        result = optimizer.execute_with_retry(unreliable_function, max_retries=5)
        print(f"   重试结果: {result}, 尝试次数: {attempt_count[0]}")
    except Exception as e:
        print(f"   重试失败: {e}")
    
    # 获取性能报告
    print("\n[DATA] 性能报告:")
    report = optimizer.get_performance_report()
    
    print(f"   缓存命中率: {report['cache']['hit_rate']:.2%}")
    print(f"   缓存大小: {report['cache']['size']}/{report['cache']['capacity']}")
    print(f"   数据库连接池: {report['connection_pools']['database']['active_connections']} 活跃")
    print(f"   任务队列大小: {report['task_scheduler']['queue_size']}")
    
    # 停止优化器
    optimizer.stop()
    
    print("\n[OK] 系统优化器测试完成！")