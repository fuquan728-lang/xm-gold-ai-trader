#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件通信模块 - 优化版
提供可靠的文件读写和锁机制
"""

import os
import time
import json
from datetime import datetime
from typing import Optional, Dict, Any
from .logger import logger
from . import config


class FileHandler:
    """优化的文件处理器"""
    
    def __init__(self):
        self._cached_path: Optional[str] = None
        self.possible_paths = config.get_possible_paths()
        self.health_check_path: Optional[str] = None
        self.last_health_check = 0.0
        self.health_check_interval = 30.0  # 30秒更新一次健康检查
    
    def update_health_check(self):
        """更新健康检查文件"""
        now = time.time()
        if now - self.last_health_check < self.health_check_interval:
            return
        
        self.last_health_check = now
        
        if self._cached_path:
            health_file = os.path.join(self._cached_path, "ai_health_check.json")
            try:
                health_data = {
                    "status": "running",
                    "timestamp": datetime.now().isoformat(),
                    "version": "v2.0"
                }
                with open(health_file, 'w', encoding='utf-16') as f:
                    json.dump(health_data, f, ensure_ascii=False)
            except Exception:
                pass
    
    def find_request_file(self) -> Optional[str]:
        """查找请求文件 - 优化版"""
        if self._cached_path:
            req_file = os.path.join(self._cached_path, "ai_request.json")
            if os.path.exists(req_file):
                return self._cached_path
        
        for base_path in self.possible_paths:
            if not os.path.exists(base_path):
                continue
            
            req_file = os.path.join(base_path, "ai_request.json")
            if os.path.exists(req_file):
                self._cached_path = base_path
                logger.debug(f"[DIR] 找到MT5路径: {base_path}")
                return base_path
            
            # 递归查找
            for root, _, files in os.walk(base_path):
                if "ai_request.json" in files:
                    self._cached_path = root
                    logger.debug(f"[DIR] 找到MT5路径: {root}")
                    return root
        
        return None
    
    def safe_read(self, file_path: str, max_wait: float = 1.0) -> Optional[str]:
        """安全读取文件 - 使用文件锁防止竞态条件"""
        if not os.path.exists(file_path):
            return None
        
        lock_file = file_path + ".lock"
        start_time = time.time()
        
        # 等待锁释放
        while os.path.exists(lock_file) and (time.time() - start_time) < max_wait:
            time.sleep(0.01)
        
        if os.path.exists(lock_file):
            logger.debug("[LOCK] 锁仍然存在，跳过这次请求")
            return None
        
        # 创建锁文件
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception:
            return None
        
        try:
            # 读取文件
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except Exception as e:
                    logger.warning(f"[WARN]  文件编码读取失败: {e}")
                    return None
            except FileNotFoundError:
                return None
            except Exception as e:
                logger.error(f"[ERR] 读取文件出错: {e}")
                return None
            
            # 删除请求文件
            try:
                os.remove(file_path)
            except Exception:
                pass
            
            return content.strip()
            
        finally:
            # 清理锁文件
            try:
                os.remove(lock_file)
            except Exception:
                pass
    
    def write_response(self, response_data: Dict[str, Any], path: str) -> bool:
        """写入响应文件 - UTF-16编码兼容EA"""
        response_file = os.path.join(path, "ai_response.json")
        
        try:
            with open(response_file, 'w', encoding='utf-16') as f:
                json.dump(response_data, f, ensure_ascii=False, separators=(',', ':'))
                f.flush()
                os.fsync(f.fileno())
            logger.debug(f"[OK] 响应已写入: {response_file}")
            return True
        except Exception as e:
            logger.error(f"[ERR] 写入响应文件失败: {e}")
            return False
    
    def cleanup_health_check(self):
        """清理健康检查文件"""
        if self._cached_path:
            health_file = os.path.join(self._cached_path, "ai_health_check.json")
            try:
                if os.path.exists(health_file):
                    health_data = {
                        "status": "stopped",
                        "timestamp": datetime.now().isoformat(),
                        "version": "v2.0"
                    }
                    with open(health_file, 'w', encoding='utf-16') as f:
                        json.dump(health_data, f, ensure_ascii=False)
            except Exception:
                pass


# 全局文件处理器
file_handler = FileHandler()
