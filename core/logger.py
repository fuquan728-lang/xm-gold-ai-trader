#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日志系统 - 优化版
提供结构化日志和性能监控
"""

import sys
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    COLORS = {
        'DEBUG': '\033[94m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m',
        'ENDC': '\033[0m'
    }
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化带颜色的日志"""
        log_color = self.COLORS.get(record.levelname, self.COLORS['ENDC'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['ENDC']}"
        return super().format(record)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.stats: Dict[str, Any] = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'average_response_time': 0.0,
            'total_response_time': 0.0,
            'cache_hits': 0,
            'cache_misses': 0,
            'start_time': datetime.now()
        }
    
    def record_request(self, success: bool, response_time: float):
        """记录一次请求"""
        self.stats['total_requests'] += 1
        if success:
            self.stats['successful_requests'] += 1
        else:
            self.stats['failed_requests'] += 1
        
        self.stats['total_response_time'] += response_time
        self.stats['average_response_time'] = (
            self.stats['total_response_time'] / self.stats['total_requests']
        )
    
    def record_cache_hit(self):
        """记录缓存命中"""
        self.stats['cache_hits'] += 1
    
    def record_cache_miss(self):
        """记录缓存未命中"""
        self.stats['cache_misses'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    
    def print_summary(self):
        """打印性能摘要"""
        stats = self.stats
        uptime = datetime.now() - stats['start_time']
        
        print("\n" + "="*60)
        print("[DATA] 性能统计摘要")
        print("="*60)
        print(f"运行时间: {uptime}")
        print(f"总请求数: {stats['total_requests']}")
        print(f"成功请求: {stats['successful_requests']}")
        print(f"失败请求: {stats['failed_requests']}")
        
        if stats['total_requests'] > 0:
            success_rate = stats['successful_requests'] / stats['total_requests'] * 100
            print(f"成功率: {success_rate:.1f}%")
            print(f"平均响应时间: {stats['average_response_time']*1000:.1f}ms")
        
        total_cache = stats['cache_hits'] + stats['cache_misses']
        if total_cache > 0:
            hit_rate = stats['cache_hits'] / total_cache * 100
            print(f"缓存命中率: {hit_rate:.1f}%")
        print("="*60 + "\n")


def setup_logger(name: str = "mt5_ai", 
                 level: int = logging.INFO,
                 log_file: Optional[str] = None) -> logging.Logger:
    """配置并返回优化后的日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 控制台处理器（彩色）
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（带轮转，防止日志无限增长）
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path,
                encoding='utf-8',
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(level)
            
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
            logger.info(f"[LOG] 日志已保存到: {log_path} (轮转: 10MB x 5)")
        except Exception as e:
            print(f"[WARN]  无法创建日志文件: {e}")
    
    return logger


# 全局日志器和监控器实例
logger = setup_logger()
monitor = PerformanceMonitor()
