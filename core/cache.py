#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存系统 - V3.1 智能分层缓存
提供多级缓存策略：热点缓存（长期）+ 标准缓存（中期）+ 临时缓存（短期）
支持缓存预热、命中率监控、自动调优
"""

import time
import threading
from collections import OrderedDict
from typing import Any, Optional, Callable, Dict, List, Tuple
from functools import wraps


class LRUCache:
    """LRU缓存实现 - 线程安全优化版"""
    
    def __init__(
        self,
        maxsize: int = 100,
        ttl: float = 300,
        *,
        max_size: Optional[int] = None,
        ttl_seconds: Optional[float] = None,
        capacity: Optional[int] = None
    ):
        """
        初始化LRU缓存
        :param maxsize: 最大缓存条目数
        :param ttl: 缓存有效期(秒)
        :param max_size: maxsize的兼容别名
        :param ttl_seconds: ttl的兼容别名
        :param capacity: maxsize的兼容别名
        """
        if max_size is not None:
            maxsize = max_size
        if capacity is not None:
            maxsize = capacity
        if ttl_seconds is not None:
            ttl = ttl_seconds
        
        self._lock = threading.RLock()
        self.cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl
        self.timestamps: Dict[str, float] = {}
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存（线程安全）"""
        with self._lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            # 检查是否过期
            if self._is_expired(key):
                self._delete(key)
                self.misses += 1
                return None
            
            self.hits += 1
            self.cache.move_to_end(key)
            return self.cache[key]
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存（线程安全）"""
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.maxsize:
                    self._evict_oldest()
            
            self.cache[key] = value
            self.timestamps[key] = time.time()
    
    def _is_expired(self, key: str) -> bool:
        """检查键是否过期（调用方需持有锁）"""
        if key not in self.timestamps:
            return True
        return (time.time() - self.timestamps[key]) > self.ttl
    
    def _delete(self, key: str) -> None:
        """删除缓存项（调用方需持有锁）"""
        self.cache.pop(key, None)
        self.timestamps.pop(key, None)
    
    def _evict_oldest(self) -> None:
        """逐出最旧的缓存项（调用方需持有锁）"""
        if self.cache:
            oldest_key = next(iter(self.cache))
            self._delete(oldest_key)
    
    def clear(self) -> None:
        """清空缓存（线程安全）"""
        with self._lock:
            self.cache.clear()
            self.timestamps.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计（线程安全）"""
        with self._lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            
            return {
                'size': len(self.cache),
                'maxsize': self.maxsize,
                'hits': self.hits,
                'misses': self.misses,
                'hit_rate': hit_rate
            }
    
    def __contains__(self, key: str) -> bool:
        """支持 'key in cache' 操作（线程安全）"""
        with self._lock:
            return key in self.cache
    
    def __len__(self) -> int:
        """支持 len(cache) 操作（线程安全）"""
        with self._lock:
            return len(self.cache)


class TieredCache:
    """
    智能分层缓存系统
    
    三级缓存策略：
    - L1 热点缓存：小容量、长TTL、LRU淘汰，存储最频繁访问的数据
    - L2 标准缓存：中等容量、中等TTL，常规数据
    - L3 临时缓存：大容量、短TTL，一次性或低频数据
    
    自动晋升/降级机制：
    - 被访问超过一定次数的L2数据自动晋升到L1
    - L1中长时间未访问的数据降级到L2
    """
    
    def __init__(
        self,
        l1_size: int = 20,
        l1_ttl: int = 600,       # 10分钟
        l2_size: int = 80,
        l2_ttl: int = 300,       # 5分钟
        l3_size: int = 200,
        l3_ttl: int = 60,        # 1分钟
        promote_threshold: int = 3,  # 访问3次晋升
        demote_threshold: int = 120  # 120秒未访问降级
    ):
        self._lock = threading.RLock()
        
        # L1: 热点缓存
        self.l1 = LRUCache(maxsize=l1_size, ttl=l1_ttl)
        # L2: 标准缓存
        self.l2 = LRUCache(maxsize=l2_size, ttl=l2_ttl)
        # L3: 临时缓存
        self.l3 = LRUCache(maxsize=l3_size, ttl=l3_ttl)
        
        # 访问计数和最后访问时间
        self.access_counts: Dict[str, int] = {}
        self.last_access: Dict[str, float] = {}
        
        # 晋升/降级阈值
        self.promote_threshold = promote_threshold
        self.demote_threshold = demote_threshold
        
        # 统计
        self.l1_hits = 0
        self.l2_hits = 0
        self.l3_hits = 0
        self.total_misses = 0
        self.promotions = 0
        self.demotions = 0
    
    def get(self, key: str) -> Optional[Any]:
        """从分层缓存获取数据"""
        with self._lock:
            # L1 查找
            if key in self.l1:
                self._record_access(key)
                self.l1_hits += 1
                return self.l1.get(key)
            
            # L2 查找
            if key in self.l2:
                value = self.l2.get(key)
                if value is not None:
                    self._record_access(key)
                    self.l2_hits += 1
                    # 检查是否需要晋升
                    self._try_promote(key, value)
                    return value
            
            # L3 查找
            if key in self.l3:
                value = self.l3.get(key)
                if value is not None:
                    self._record_access(key)
                    self.l3_hits += 1
                    return value
            
            self.total_misses += 1
            return None
    
    def set(self, key: str, value: Any, tier: str = "auto") -> None:
        """
        设置缓存数据
        
        :param key: 缓存键
        :param value: 缓存值
        :param tier: 指定层级 "l1"/"l2"/"l3"/"auto"
        """
        with self._lock:
            # 初始化访问记录
            if key not in self.access_counts:
                self.access_counts[key] = 0
            self.last_access[key] = time.time()
            
            if tier == "l1":
                self.l1.set(key, value)
            elif tier == "l3":
                self.l3.set(key, value)
            else:
                # auto 或 l2: 默认放入L2
                self.l2.set(key, value)
    
    def _record_access(self, key: str) -> None:
        """记录访问（调用方需持有锁）"""
        self.access_counts[key] = self.access_counts.get(key, 0) + 1
        self.last_access[key] = time.time()
    
    def _try_promote(self, key: str, value: Any) -> None:
        """尝试晋升缓存（调用方需持有锁）"""
        count = self.access_counts.get(key, 0)
        if count >= self.promote_threshold:
            self.l1.set(key, value)
            # 从L2移除
            self.l2.cache.pop(key, None)
            self.l2.timestamps.pop(key, None)
            self.promotions += 1
    
    def _try_demote(self) -> None:
        """定期清理：将L1中冷数据降级（调用方需持有锁）"""
        now = time.time()
        keys_to_demote = []
        
        for key in list(self.l1.cache.keys()):
            last = self.last_access.get(key, 0)
            if now - last > self.demote_threshold:
                keys_to_demote.append(key)
        
        for key in keys_to_demote:
            value = self.l1.get(key)
            if value is not None:
                self.l2.set(key, value)
                self.l1.cache.pop(key, None)
                self.l1.timestamps.pop(key, None)
                self.demotions += 1
    
    def cleanup(self) -> None:
        """执行缓存维护：降级冷数据 + 清理访问记录"""
        with self._lock:
            self._try_demote()
            
            # 清理过期的访问记录（防止内存泄漏）
            now = time.time()
            stale_keys = [
                k for k, t in self.last_access.items()
                if now - t > 3600 and k not in self.l1.cache and k not in self.l2.cache
            ]
            for k in stale_keys:
                self.access_counts.pop(k, None)
                self.last_access.pop(k, None)
    
    def warmup(self, data: Dict[str, Any]) -> int:
        """
        缓存预热：批量加载热点数据到L1
        
        :param data: {key: value} 字典
        :return: 预热的条目数
        """
        with self._lock:
            count = 0
            for key, value in data.items():
                self.l1.set(key, value)
                self.access_counts[key] = self.promote_threshold  # 标记为热点
                self.last_access[key] = time.time()
                count += 1
            return count
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self.l1.clear()
            self.l2.clear()
            self.l3.clear()
            self.access_counts.clear()
            self.last_access.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取完整的缓存统计"""
        with self._lock:
            total_hits = self.l1_hits + self.l2_hits + self.l3_hits
            total_requests = total_hits + self.total_misses
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
            
            l1_stats = self.l1.get_stats()
            l2_stats = self.l2.get_stats()
            l3_stats = self.l3.get_stats()
            
            return {
                'total_hit_rate': round(hit_rate, 2),
                'total_requests': total_requests,
                'total_hits': total_hits,
                'total_misses': self.total_misses,
                'l1': {**l1_stats, 'name': '热点缓存'},
                'l2': {**l2_stats, 'name': '标准缓存'},
                'l3': {**l3_stats, 'name': '临时缓存'},
                'promotions': self.promotions,
                'demotions': self.demotions,
                'access_records': len(self.access_counts)
            }
    
    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self.l1 or key in self.l2 or key in self.l3
    
    def __len__(self) -> int:
        with self._lock:
            return len(self.l1) + len(self.l2) + len(self.l3)


def cached(maxsize: int = 100, ttl: int = 300):
    """缓存装饰器（兼容旧代码）"""
    cache = LRUCache(maxsize, ttl)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_cache_key(args, kwargs)
            value = cache.get(key)
            
            if value is not None:
                return value
            
            value = func(*args, **kwargs)
            cache.set(key, value)
            return value
        
        return wrapper
    return decorator


def _make_cache_key(args: tuple, kwargs: dict) -> str:
    """生成缓存键"""
    key_parts = [str(arg) for arg in args]
    key_parts.extend(f"{k}:{v}" for k, v in sorted(kwargs.items()))
    return "|".join(key_parts)


# 全局缓存实例 - 向后兼容
global_cache = LRUCache(maxsize=100, ttl=300)

# 分层缓存实例 - 新代码使用
tiered_cache = TieredCache()
