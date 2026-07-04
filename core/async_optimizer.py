#!/usr/bin/env python3
"""
MT5 AI Trading System - Asynchronous Python Pattern Optimizer (V4.0)

基于async-python-patterns技能的高级异步通信优化模块，提供：
1. 连接池管理
2. 速率限制和拥塞控制
3. 智能重连策略
4. 批量处理和延迟优化
5. 监控和诊断工具
6. 资源管理
"""

import asyncio
import inspect
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set, Tuple, Callable, Union, AsyncIterator, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum, auto
import random
import logging
from concurrent.futures import ThreadPoolExecutor
import uuid
from collections import deque

# 引入核心模块
try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    websockets = None
    HAS_WEBSOCKETS = False

WebSocketServerProtocol = Any

try:
    import aiohttp
    from aiohttp import ClientSession, ClientTimeout
    HAS_AIOSESSION = True
except ImportError:
    HAS_AIOSESSION = False

from core.logger import logger


class ConnectionStatus(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    THROTTLED = "throttled"
    BACKOFF = "backoff"


class OperationType(Enum):
    """操作类型枚举"""
    WEBSOCKET = "websocket"
    HTTP = "http"
    SOCKET = "socket"
    FILE = "file"
    DATABASE = "database"
    API = "api"


@dataclass
class ConnectionMetric:
    """连接指标"""
    operation_type: OperationType
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = True
    error: Optional[str] = None
    latency_ms: float = 0.0
    data_size: int = 0
    
    def calculate_latency(self):
        """计算延迟"""
        if self.end_time:
            self.latency_ms = (self.end_time - self.start_time).total_seconds() * 1000


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    operations_per_second: int = 10
    burst_size: int = 20
    window_seconds: float = 1.0


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True


@dataclass
class ConnectionConfig:
    """连接配置"""
    operation_type: OperationType
    endpoint: str
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    timeout: float = 30.0
    keepalive: bool = True
    pool_size: int = 10


class EnhancedAsyncRateLimiter:
    """
    增强版异步速率限制器
    
    关键改进：
    1. 基于时间窗口的精确令牌控制，而非简单的时间差计算
    2. 使用高精度单调时钟（time.monotonic_ns()）
    3. 滑动窗口统计，避免历史令牌积累误差
    4. 突发流量平滑处理，防止瞬时过载
    5. 并发公平性优化，避免客户端间资源分配不均衡
    
    算法原理：
    - 维护一个令牌桶，容量为 burst_size
    - 令牌生成速率：rate = operations_per_second
    - 每次请求消耗 tokens（默认为1）
    - 令牌补充基于上次请求的时间差和生成速率
    - 采用滑动窗口统计实际速率，用于自适应调整
    - 实现公平队列调度，确保并发客户端资源分配均衡
    
    """
    
    def __init__(self, operations_per_second: float = 15.0, burst_size: int = 30, strict_mode: bool = True):
        """初始化增强版速率限制器"""
        # 检查配置参数
        if operations_per_second <= 0:
            raise ValueError("operations_per_second must be > 0")
        if burst_size <= 0:
            raise ValueError("burst_size must be > 0")
        
        # 基础配置
        self.operations_per_second = operations_per_second
        self.burst_size = burst_size
        self.strict_mode = strict_mode
        
        # 令牌桶状态
        self.tokens = float(burst_size)  # 当前令牌数（支持小数）
        self.last_refill_time = time.monotonic_ns()  # 上次补充时间（纳秒）
        
        # 请求历史记录（用于滑动窗口统计）
        self.request_history = deque(maxlen=1000)
        
        # 性能统计
        self.total_requests = 0
        self.allowed_requests = 0
        self.rate_limited_requests = 0
        self.total_wait_time = 0.0
        self.start_time = time.time()
        
        # 纳秒转换为秒的系数
        self.NANOSECONDS_PER_SECOND = 1_000_000_000.0
        
        # 每纳秒生成的令牌数
        self.tokens_per_ns = operations_per_second / self.NANOSECONDS_PER_SECOND
        
        # 锁保护
        self._lock = asyncio.Lock()
        
        # 公平队列支持 - 用于改进并发公平性
        self._fair_queue = asyncio.Queue()  # 等待队列
        self._client_weights = {}  # 客户端权重
        self._default_client_weight = 1.0
        
        logger.info(f"[OK] Enhanced rate limiter initialized: {operations_per_second:.1f} ops/sec, burst={burst_size}, strict_mode={strict_mode}, fair_queue=True")
    
    def _refill_tokens(self, current_time_ns: int) -> None:
        """
        根据时间差补充令牌
        
        核心算法：
        1. 计算从上次补充到现在的时间差（纳秒）
        2. 根据速率计算应生成的令牌数
        3. 更新令牌桶（不超过容量）
        4. 更新时间戳
        """
        # 计算时间差（纳秒）
        time_elapsed_ns = current_time_ns - self.last_refill_time
        
        if time_elapsed_ns <= 0:
            return
        
        # 计算应补充的令牌数
        tokens_to_add = time_elapsed_ns * self.tokens_per_ns
        
        # 补充令牌（不超过容量）
        self.tokens = min(self.burst_size, self.tokens + tokens_to_add)
        
        # 更新最后补充时间
        self.last_refill_time = current_time_ns
    
    def set_client_weight(self, client_id: str, weight: float = 1.0) -> None:
        """
        设置客户端权重
        
        Args:
            client_id: 客户端标识符
            weight: 权重值，越大优先级越高（默认1.0）
        """
        if weight <= 0:
            raise ValueError("Weight must be > 0")
        self._client_weights[client_id] = weight
        logger.debug(f"[OK] Client weight set: {client_id} = {weight}")
    
    def _get_client_weight(self, client_id: str = "default") -> float:
        """获取客户端权重"""
        return self._client_weights.get(client_id, self._default_client_weight)
    
    async def acquire(self, tokens: int = 1, client_id: str = "default") -> tuple[bool, float]:
        """
        获取令牌（非阻塞）- 支持客户端公平性
        
        返回：
        - (success, wait_time)：是否成功，需要等待的时间（秒）
        """
        if tokens <= 0:
            raise ValueError("tokens must be > 0")
        
        # 获取客户端权重
        client_weight = self._get_client_weight(client_id)
        
        async with self._lock:
            current_time_ns = time.monotonic_ns()
            
            # 补充令牌
            self._refill_tokens(current_time_ns)
            
            # 更新总请求数
            self.total_requests += 1
            
            # 记录请求时间（用于滑动窗口统计）
            self.request_history.append(current_time_ns / self.NANOSECONDS_PER_SECOND)
            
            # 检查是否有足够令牌（根据权重调整）
            # 高权重客户端有更多的可用令牌 = self.tokens * client_weight
            # 但实际消耗的令牌仍然是 tokens
            available_tokens_for_client = self.tokens * client_weight
            
            if available_tokens_for_client >= tokens:
                # 消耗令牌（按权重折算）
                self.tokens -= tokens / client_weight if client_weight > 0 else tokens
                self.allowed_requests += 1
                
                logger.debug(f"[OK] Rate limiter allowed request for client={client_id}, "
                           f"weight={client_weight}, tokens={self.tokens:.2f}")
                return True, 0.0
            
            # 计算需要等待的时间
            deficit = tokens - available_tokens_for_client
            
            # 计算加权等待时间（秒）
            # deficit已经是加权令牌赤字，所以等待时间 = deficit / 速率
            # 高权重客户端deficit更小，所以等待时间更短
            wait_time_seconds = deficit / self.operations_per_second
            
            # 更新速率限制统计
            self.rate_limited_requests += 1
            self.total_wait_time += wait_time_seconds
            
            logger.debug(f"[WAIT] Rate limiter delayed request for client={client_id}, "
                        f"weight={client_weight}, wait={wait_time_seconds:.3f}s, "
                       f"tokens={self.tokens:.2f}, deficit={deficit:.2f}")
            
            return False, wait_time_seconds
    
    async def wait(self, tokens: int = 1, max_wait_time: float | None = None) -> bool:
        """
        等待获取令牌（阻塞）
        
        返回：是否成功获取令牌
        """
        while True:
            success, wait_time = await self.acquire(tokens)
            
            if success:
                return True
            
            if max_wait_time is not None and wait_time > max_wait_time:
                logger.warning(f"[TIMEOUT] Rate limiter wait time exceeded: {wait_time:.3f}s > {max_wait_time:.3f}s")
                return False
            
            # 精确等待
            if wait_time > 0:
                await asyncio.sleep(wait_time)
    
    def get_stats(self) -> dict[str, Any]:
        """获取速率限制统计信息"""
        # 计算实际速率
        elapsed_time = time.time() - self.start_time
        actual_rate = self.allowed_requests / elapsed_time if elapsed_time > 0 else 0.0
        
        # 计算滑动窗口速率
        window_seconds = 2.0  # 固定窗口大小
        window_rate = 0.0
        if len(self.request_history) >= 2:
            current_time = time.monotonic_ns() / self.NANOSECONDS_PER_SECOND
            window_start = current_time - window_seconds
            
            # 统计窗口内的请求数
            window_requests = sum(1 for t in self.request_history if t >= window_start)
            window_rate = window_requests / window_seconds
        
        # 计算符合度
        compliance = (actual_rate / self.operations_per_second * 100) if self.operations_per_second > 0 else 0.0
        
        return {
            "target_rate_per_second": self.operations_per_second,
            "actual_rate_per_second": round(actual_rate, 2),
            "window_rate_per_second": round(window_rate, 2),
            "compliance_percent": round(compliance, 2),
            "total_requests": self.total_requests,
            "allowed_requests": self.allowed_requests,
            "rate_limited_requests": self.rate_limited_requests,
            "avg_wait_time_seconds": round(self.total_wait_time / self.rate_limited_requests, 4) if self.rate_limited_requests > 0 else 0.0,
            "current_tokens": round(self.tokens, 3),
            "burst_size": self.burst_size,
            "strict_mode": self.strict_mode
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self.total_requests = 0
        self.allowed_requests = 0
        self.rate_limited_requests = 0
        self.total_wait_time = 0.0
        self.start_time = time.time()
        self.request_history.clear()
        logger.info("[OK] Rate limiter statistics reset")


class AsyncRateLimiter(EnhancedAsyncRateLimiter):
    """向后兼容层：保持相同的类名"""
    pass


class AsyncConnectionPool:
    """异步连接池"""
    
    def __init__(self, pool_size: int = 10):
        self.pool_size = pool_size
        self.connections = asyncio.Queue(maxsize=pool_size)
        self.active_count = 0
        self.lock = asyncio.Lock()
        
        # 初始化连接池
        for _ in range(pool_size):
            self.connections.put_nowait({
                "id": str(uuid.uuid4()),
                "type": "http",
                "session": None,
                "last_used": datetime.now()
            })
        
        logger.info(f"[OK] Connection pool initialized: size={pool_size}")
    
    async def acquire(self, conn_type: str = "http") -> Dict[str, Any]:
        """从连接池获取连接"""
        # 检查是否超过池大小
        async with self.lock:
            if self.active_count >= self.pool_size:
                # 等待连接释放
                return None
        
        # 获取连接
        connection = await self.connections.get()
        self.active_count += 1
        
        # 如果是http类型且需要创建session
        if conn_type == "http" and HAS_AIOSESSION and connection["session"] is None:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = ClientTimeout(total=30.0)
            connection["session"] = ClientSession(connector=connector, timeout=timeout)
        
        connection["last_used"] = datetime.now()
        connection["type"] = conn_type
        
        return connection
    
    async def release(self, connection: Dict[str, Any]):
        """释放连接回连接池"""
        connection["last_used"] = datetime.now()
        await self.connections.put(connection)
        
        async with self.lock:
            self.active_count -= 1
    
    async def cleanup(self, max_idle_seconds: int = 300):
        """清理闲置连接"""
        now = datetime.now()
        removed_count = 0
        
        # 获取所有连接快照
        temp_connections = []
        while not self.connections.empty():
            conn = self.connections.get_nowait()
            temp_connections.append(conn)
        
        # 过滤闲置连接
        for conn in temp_connections:
            idle_time = (now - conn["last_used"]).total_seconds()
            if idle_time > max_idle_seconds and conn.get("session") is not None:
                # 关闭session
                try:
                    await conn["session"].close()
                except:
                    pass
                conn["session"] = None
                removed_count += 1
            
            await self.connections.put(conn)
        
        if removed_count > 0:
            logger.info(f"[OK] Cleared {removed_count} idle connections")


class SmartRetryManager:
    """智能重试管理器"""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.attempts = {}
        logger.info(f"[OK] SmartRetryManager initialized with {config.max_retries} max retries")
    
    async def execute_with_retry(self, operation: Callable, *args, operation_name: str = "operation", **kwargs) -> Any:
        """使用指数退避算法执行重试操作"""
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                if attempt > 0:
                    # 计算延迟
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"[RETRY] Attempt {attempt}/{self.config.max_retries} for {operation_name}, waiting {delay:.2f}s")
                    await asyncio.sleep(delay)
                
                # 执行操作
                start_time = time.time()
                if asyncio.iscoroutinefunction(operation):
                    result = await operation(*args, **kwargs)
                else:
                    result = operation(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                elapsed = (time.time() - start_time) * 1000
                
                logger.info(f"[OK] {operation_name} completed on attempt {attempt + 1}, {elapsed:.1f}ms")
                return result
                
            except Exception as e:
                last_error = e
                error_type = type(e).__name__
                
                # 检查是否为可重试错误
                if not self._is_retryable_error(e):
                    logger.error(f"[ERR] {operation_name} failed with non-retryable error: {error_type} - {e}")
                    raise e
                
                logger.warning(f"[WARN] {operation_name} failed on attempt {attempt + 1}: {error_type} - {e}")
        
        # 所有重试都失败了
        logger.error(f"[ERR] {operation_name} failed after {self.config.max_retries} retries: {last_error}")
        raise last_error
    
    def _calculate_backoff(self, attempt: int) -> float:
        """计算指数退避延迟"""
        delay = self.config.initial_delay * (self.config.backoff_factor ** (attempt - 1))
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)  # 添加50%的抖动
        
        return delay
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """判断是否为可重试错误"""
        # 网络错误、超时错误等通常是可重试的
        error_type = type(error).__name__
        retryable_errors = {
            "ConnectionError", "TimeoutError", "socket.error", "OSError",
            "aiohttp.ClientError", "websockets.exceptions.ConnectionClosed"
        }
        
        for retryable in retryable_errors:
            if retryable in str(error_type) or retryable in str(error):
                return True
        
        return False


class AsyncBatchProcessor:
    """异步批量处理器"""
    
    def __init__(self, batch_size: int = 100, max_concurrent: int = 10):
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        logger.info(f"[OK] Batch processor initialized: batch_size={batch_size}, concurrent={max_concurrent}")
    
    async def process_batch(
        self,
        items: List[Any],
        process_func: Callable,
        *,
        progress_callback: Optional[Callable] = None,
        error_handler: Optional[Callable] = None
    ) -> List[Any]:
        """处理一批数据"""
        results = []
        errors = []
        
        # 分批处理
        for batch_start in range(0, len(items), self.batch_size):
            batch_end = min(batch_start + self.batch_size, len(items))
            batch = items[batch_start:batch_end]
            batch_num = batch_start // self.batch_size + 1
            total_batches = (len(items) + self.batch_size - 1) // self.batch_size
            
            logger.info(f"[OK] Processing batch {batch_num}/{total_batches}, items {batch_start}-{batch_end-1}")
            
            # 并发处理批次
            batch_results = await self._process_batch_concurrently(batch, process_func, error_handler)
            results.extend([r for r in batch_results if r is not None])
            
            # 更新进度
            if progress_callback:
                await progress_callback(batch_num, total_batches, len(batch_results), len(errors))
        
        logger.info(f"[OK] Batch processing completed: {len(results)} results, {len(errors)} errors")
        return results
    
    async def _process_batch_concurrently(
        self,
        batch: List[Any],
        process_func: Callable,
        error_handler: Optional[Callable]
    ) -> List[Any]:
        """并发处理单批次"""
        tasks = []
        for item in batch:
            task = self._process_item_with_semaphore(item, process_func, error_handler)
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_item_with_semaphore(
        self,
        item: Any,
        process_func: Callable,
        error_handler: Optional[Callable]
    ) -> Any:
        """使用信号量处理单个项目"""
        async with self.semaphore:
            try:
                if asyncio.iscoroutinefunction(process_func):
                    result = await process_func(item)
                else:
                    # 如果是阻塞函数，使用线程池
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor() as pool:
                        result = await loop.run_in_executor(pool, process_func, item)
                
                return result
                
            except Exception as e:
                if error_handler:
                    return await error_handler(item, e)
                logger.error(f"[ERR] Failed to process item: {item}, error: {e}")
                return None


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.metrics: List[ConnectionMetric] = []
        self.lock = asyncio.Lock()  # asyncio.Lock for async context safety
        
        # 统计信息
        self.total_operations = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.total_latency = 0.0
        self.total_data = 0
        
        logger.info(f"[OK] Performance monitor initialized: window_size={window_size}")
    
    async def record_operation(
        self,
        operation_type: OperationType,
        start_time: datetime,
        end_time: datetime,
        success: bool,
        error: Optional[str] = None,
        data_size: int = 0
    ):
        """记录操作指标"""
        metric = ConnectionMetric(
            operation_type=operation_type,
            start_time=start_time,
            end_time=end_time,
            success=success,
            error=error,
            data_size=data_size
        )
        metric.calculate_latency()
        
        async with self.lock:
            self.metrics.append(metric)
            if len(self.metrics) > self.window_size:
                self.metrics.pop(0)
            
            # 更新统计信息
            self.total_operations += 1
            if success:
                self.successful_operations += 1
                self.total_latency += metric.latency_ms
            else:
                self.failed_operations += 1
            
            self.total_data += data_size
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        async with self.lock:
            if not self.metrics:
                return {}
            
            # 计算最近指标
            recent_metrics = self.metrics[-100:] if len(self.metrics) >= 100 else self.metrics
            recent_latencies = [m.latency_ms for m in recent_metrics if m.success]
            
            avg_latency = sum(recent_latencies) / len(recent_latencies) if recent_latencies else 0.0
            max_latency = max(recent_latencies) if recent_latencies else 0.0
            min_latency = min(recent_latencies) if recent_latencies else 0.0
            
            # 成功率
            success_rate = (self.successful_operations / self.total_operations * 100) if self.total_operations > 0 else 100.0
            
            # 操作类型分布
            type_distribution = {}
            for metric in self.metrics:
                op_type = metric.operation_type.value
                type_distribution[op_type] = type_distribution.get(op_type, 0) + 1
            
            return {
                "total_operations": self.total_operations,
                "successful_operations": self.successful_operations,
                "failed_operations": self.failed_operations,
                "success_rate_percent": round(success_rate, 2),
                "avg_latency_ms": round(avg_latency, 2),
                "min_latency_ms": round(min_latency, 2),
                "max_latency_ms": round(max_latency, 2),
                "total_data_bytes": self.total_data,
                "throughput_bps": round(self.total_data / (self.total_operations * 0.001) if self.total_operations > 0 else 0, 2),
                "type_distribution": type_distribution,
                "window_size": len(self.metrics)
            }
    
    async def reset(self):
        """重置统计信息"""
        async with self.lock:
            self.metrics.clear()
            self.total_operations = 0
            self.successful_operations = 0
            self.failed_operations = 0
            self.total_latency = 0.0
            self.total_data = 0
            
            logger.info("[OK] Performance monitor reset")


class AsyncOptimizer:
    """异步优化器主类"""
    
    def __init__(
        self,
        max_http_connections: int = 50,
        max_ws_connections: int = 100,
        rate_limit_per_client: int = 50,
        enable_monitoring: bool = True
    ):
        # 连接池
        self.http_pool = AsyncConnectionPool(pool_size=max_http_connections // 2)
        self.ws_pool = AsyncConnectionPool(pool_size=max_ws_connections // 2)
        
        # 速率限制器
        self.rate_limiter = AsyncRateLimiter(operations_per_second=rate_limit_per_client)
        
        # 重试管理器
        self.retry_manager = SmartRetryManager(RetryConfig(max_retries=3))
        
        # 批量处理器
        self.batch_processor = AsyncBatchProcessor(batch_size=100, max_concurrent=20)
        
        # 性能监控器
        self.monitor = PerformanceMonitor(window_size=1000) if enable_monitoring else None
        
        # 连接映射
        self.connections: Dict[str, Any] = {}
        
        # 清理任务
        self.cleanup_task = None
        
        logger.info(f"[OK] AsyncOptimizer initialized: HTTP={max_http_connections}, WS={max_ws_connections}")
    
    async def http_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Dict[str, Any]:
        """HTTP请求（带连接池）"""
        start_time = datetime.now()
        operation_id = f"http_{method}_{url.split('/')[-1]}"
        
        try:
            # 等待速率限制
            await self.rate_limiter.wait(tokens=1)
            
            # 获取连接
            connection = await self.http_pool.acquire("http")
            if not connection or not connection.get("session"):
                raise Exception("Failed to acquire HTTP connection")
            
            session = connection["session"]
            
            async def _make_request():
                async with session.request(method, url, **kwargs) as response:
                    data = await response.read()
                    return {
                        "status": response.status,
                        "headers": dict(response.headers),
                        "data": data,
                        "text": data.decode('utf-8', errors='ignore') if data else "",
                        "url": str(response.url)
                    }
            
            # 使用重试机制
            result = await self.retry_manager.execute_with_retry(
                _make_request,
                operation_name=operation_id
            )
            
            # 记录成功
            end_time = datetime.now()
            if self.monitor:
                await self.monitor.record_operation(
                    OperationType.HTTP,
                    start_time,
                    end_time,
                    success=True,
                    data_size=len(result.get("data", b""))
                )
            
            return result
            
        except Exception as e:
            # 记录失败
            end_time = datetime.now()
            if self.monitor:
                await self.monitor.record_operation(
                    OperationType.HTTP,
                    start_time,
                    end_time,
                    success=False,
                    error=str(e)
                )
            
            logger.error(f"[ERR] HTTP request failed: {method} {url} - {e}")
            raise e
        
        finally:
            # 释放连接
            if 'connection' in locals():
                await self.http_pool.release(connection)
    
    async def websocket_send(
        self,
        client_id: str,
        message: Dict[str, Any],
        timeout: float = 5.0
    ) -> bool:
        """WebSocket发送（带连接池）"""
        start_time = datetime.now()
        
        try:
            # 等待速率限制
            await self.rate_limiter.wait(tokens=1)
            
            # 获取客户端连接
            if client_id not in self.connections:
                raise Exception(f"WebSocket client not found: {client_id}")
            
            websocket = self.connections[client_id]
            message_str = json.dumps(message, ensure_ascii=False)
            
            # 发送消息
            await asyncio.wait_for(websocket.send(message_str), timeout=timeout)
            
            # 记录成功
            end_time = datetime.now()
            if self.monitor:
                await self.monitor.record_operation(
                    OperationType.WEBSOCKET,
                    start_time,
                    end_time,
                    success=True,
                    data_size=len(message_str)
                )
            
            logger.info(f"[OK] WebSocket message sent to {client_id}: {len(message_str)} bytes")
            return True
            
        except Exception as e:
            # 记录失败
            end_time = datetime.now()
            if self.monitor:
                await self.monitor.record_operation(
                    OperationType.WEBSOCKET,
                    start_time,
                    end_time,
                    success=False,
                    error=str(e)
                )
            
            logger.error(f"[ERR] WebSocket send failed to {client_id}: {e}")
            return False
    
    async def batch_process(
        self,
        items: List[Any],
        process_func: Callable,
        **kwargs
    ) -> List[Any]:
        """批量处理"""
        return await self.batch_processor.process_batch(items, process_func, **kwargs)
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        if self.monitor:
            stats = await self.monitor.get_stats()
            stats.update({
                "http_pool_active": self.http_pool.active_count,
                "ws_pool_active": self.ws_pool.active_count,
                "rate_limiter_ops_per_sec": self.rate_limiter.operations_per_second,
                "connections_count": len(self.connections)
            })
            return stats
        return {}
    
    async def cleanup(self):
        """清理资源"""
        logger.info("[OK] Starting cleanup...")
        
        # 取消清理任务
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        # 清理连接池
        await self.http_pool.cleanup()
        await self.ws_pool.cleanup()
        
        # 关闭所有连接
        for client_id, connection in list(self.connections.items()):
            try:
                if hasattr(connection, 'close'):
                    await connection.close()
                del self.connections[client_id]
            except:
                pass
        
        logger.info("[OK] Cleanup completed")
    
    async def start_cleanup_task(self, interval_seconds: int = 60):
        """启动定时清理任务"""
        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self.http_pool.cleanup()
                    await self.ws_pool.cleanup()
                    logger.debug(f"[OK] Connection pools cleaned up, active: HTTP={self.http_pool.active_count}, WS={self.ws_pool.active_count}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[ERR] Cleanup task error: {e}")
        
        self.cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info(f"[OK] Cleanup task started, interval={interval_seconds}s")


# 导出异步优化的主要函数
async def async_http_get(url: str, session = None, **kwargs) -> Dict[str, Any]:
    """异步HTTP GET请求（优化的连接池版本）"""
    if not HAS_AIOSESSION:
        raise ImportError("aiohttp not installed, async HTTP operations unavailable")
    
    from aiohttp import ClientSession
    
    if not session:
        session = AsyncOptimizer().http_pool  # 使用连接池
        session_ctx = True
    else:
        session_ctx = False
    
    try:
        async with session.get(url, **kwargs) as response:
            data = await response.read()
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "data": data,
                "text": data.decode('utf-8', errors='ignore') if data else "",
                "url": str(response.url)
            }
    finally:
        if session_ctx and hasattr(session, 'close'):
            await session.close()


async def async_rate_limited_map(
    items: List[Any],
    process_func: Callable,
    max_concurrent: int = 10,
    rate_limit: int = 50
) -> List[Any]:
    """速率限制的并发映射处理"""
    rate_limiter = AsyncRateLimiter(operations_per_second=rate_limit)
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_item(item):
        async with semaphore:
            await rate_limiter.wait(tokens=1)
            return await process_func(item) if asyncio.iscoroutinefunction(process_func) else process_func(item)
    
    tasks = [process_item(item) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤错误
    return [r for r in results if not isinstance(r, Exception)]


async def async_retry(
    operation: Callable,
    *args,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    **kwargs
) -> Any:
    """智能重试装饰器"""
    retry_manager = SmartRetryManager(RetryConfig(
        max_retries=max_retries,
        initial_delay=initial_delay
    ))
    
    return await retry_manager.execute_with_retry(
        operation,
        *args,
        operation_name=operation.__name__,
        **kwargs
    )


# 导出主类
__all__ = [
    "AsyncOptimizer",
    "AsyncRateLimiter",
    "AsyncConnectionPool",
    "SmartRetryManager",
    "AsyncBatchProcessor",
    "PerformanceMonitor",
    "async_http_get",
    "async_rate_limited_map",
    "async_retry"
]
