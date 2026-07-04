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

    def _atomic_write_json(self, filepath: str, data: Dict[str, Any], encoding: str = "utf-16") -> bool:
        """Write JSON via temp file + os.replace so readers never see partial JSON."""
        tmp_file = filepath + ".tmp"
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(tmp_file, 'w', encoding=encoding) as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, filepath)
            return True
        except Exception as e:
            logger.error(f"[ERR] Atomic JSON write failed: {filepath}: {e}")
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception:
                pass
            return False
    
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
                self._atomic_write_json(health_file, health_data)
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
    
    def safe_read(self, file_path: str, max_wait: float = 5.0, retries: int = 2) -> Optional[str]:
        """安全读取文件 - 使用文件锁防止竞态条件
        
        Args:
            file_path: 要读取的文件路径
            max_wait: 单次等待锁释放的最大秒数（默认5.0s）
            retries: 锁被占用时的最大重试次数（默认2次，每次间隔200ms递增）
        """
        if not os.path.exists(file_path):
            return None
        
        lock_file = file_path + ".lock"
        
        for attempt in range(retries + 1):
            # 清理孤儿锁（超过60秒未释放的锁视为孤儿）
            if os.path.exists(lock_file):
                try:
                    lock_age = time.time() - os.path.getmtime(lock_file)
                    if lock_age > 60.0:
                        logger.warning(f"[LOCK] 清理孤儿锁文件 (已存在 {lock_age:.0f}s): {lock_file}")
                        os.remove(lock_file)
                except OSError:
                    pass
            
            start_time = time.time()
            
            # 等待锁释放
            while os.path.exists(lock_file) and (time.time() - start_time) < max_wait:
                time.sleep(0.01)
            
            if not os.path.exists(lock_file):
                break  # 锁已释放
            
            if attempt < retries:
                backoff = 0.2 * (attempt + 1)
                logger.debug(f"[LOCK] 锁仍被占用，{backoff:.1f}s后重试 ({attempt+1}/{retries}): {lock_file}")
                time.sleep(backoff)
                continue
        
        if os.path.exists(lock_file):
            logger.warning(f"[LOCK] 重试{retries}次后锁仍被占用，丢弃请求: {lock_file}")
            return None
        
        # 创建锁文件
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
        except Exception:
            return None
        
        try:
            # 读取文件 — EA 写入 UTF-16 LE，故优先尝试 UTF-16
            try:
                with open(file_path, 'r', encoding='utf-16') as f:
                    content = f.read()
            except UnicodeDecodeError:
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
            if not self._atomic_write_json(response_file, response_data):
                return False
            logger.debug(f"[OK] 响应已写入: {response_file}")
            return True
        except Exception as e:
            logger.error(f"[ERR] 写入响应文件失败: {e}")
            return False

    def write_service_ready(self, path: str, service_id: str, mode: str, ready: bool = True) -> bool:
        """Publish service readiness for EA ready gate."""
        ready_file = os.path.join(path, "service_ready.json")
        ready_data = {
            "ready": bool(ready),
            "service_id": service_id,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
        }
        ok = self._atomic_write_json(ready_file, ready_data)
        if ok:
            self._cached_path = path
        return ok

    def publish_ready_to_known_paths(self, service_id: str, mode: str) -> int:
        """Best-effort ready publication to configured MT5 Files paths."""
        published = 0
        original_cached_path = self._cached_path
        candidate_paths = []
        if self._cached_path:
            candidate_paths.append(self._cached_path)
        candidate_paths.extend(self.possible_paths)

        seen = set()
        for path in candidate_paths:
            if not path or path in seen:
                continue
            seen.add(path)
            if not os.path.isdir(path):
                continue
            if self.write_service_ready(path, service_id, mode, ready=True):
                published += 1
        self._cached_path = original_cached_path
        return published
    
    def write_json_to_file(self, filename: str, data: Dict[str, Any]) -> bool:
        """写入通用JSON文件到MT5 Files目录（UTF-16编码兼容EA）
        
        Args:
            filename: 目标文件名（如 close_order.json, crisis_stop.json）
            data: 要写入的数据字典
        Returns:
            bool: 写入是否成功
        """
        if not self._cached_path:
            logger.error("[ERR] No cached MT5 Files path available")
            return False
        
        filepath = os.path.join(self._cached_path, filename)
        try:
            if not self._atomic_write_json(filepath, data):
                return False
            logger.debug(f"[OK] Written: {filepath}")
            return True
        except Exception as e:
            logger.error(f"[ERR] Failed to write {filename}: {e}")
            return False
    
    def read_json_from_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """从MT5 Files目录读取JSON文件
        
        Args:
            filename: 源文件名
        Returns:
            dict or None: 读取的数据，失败返回None
        """
        if not self._cached_path:
            return None
        
        filepath = os.path.join(self._cached_path, filename)
        try:
            if not os.path.exists(filepath):
                return None
            with open(filepath, 'r', encoding='utf-16') as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Failed to read {filename}: {e}")
            return None
    
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
                    self._atomic_write_json(health_file, health_data)
            except Exception:
                pass

            ready_file = os.path.join(self._cached_path, "service_ready.json")
            try:
                if os.path.exists(ready_file):
                    ready_data = {
                        "ready": False,
                        "timestamp": datetime.now().isoformat(),
                        "version": "v2.0"
                    }
                    self._atomic_write_json(ready_file, ready_data)
            except Exception:
                pass


# 全局文件处理器
file_handler = FileHandler()
