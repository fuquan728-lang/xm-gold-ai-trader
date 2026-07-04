#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP客户端 - 优化版
提供高性能的HTTP请求和连接池管理
"""

import requests
import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, Any
from .logger import logger
from . import config


class HTTPClient:
    """优化后的HTTP客户端"""
    
    def __init__(self, max_retries: Optional[int] = None, 
                 pool_size: Optional[int] = None, 
                 timeout: Optional[int] = None):
        # 使用配置中的默认值
        self.max_retries = max_retries if max_retries is not None else config.MAX_RETRIES
        self.pool_size = pool_size if pool_size is not None else config.CONNECTION_POOL_SIZE
        self.timeout = timeout if timeout is not None else config.REQUEST_TIMEOUT
        self.session = self._create_session(self.max_retries, self.pool_size)
    
    def _create_session(self, max_retries: int, pool_size: int) -> requests.Session:
        """创建带连接池的会话"""
        session = requests.Session()
        
        try:
            retry_strategy = Retry(
                total=max_retries,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=pool_size,
                pool_maxsize=pool_size,
                pool_block=False
            )
            
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            
            logger.info("[OK] HTTP连接池初始化成功")
            
        except Exception as e:
            logger.warning(f"[WARN]  连接池初始化失败: {e}，使用基础请求")
        
        return session
    
    def post(self, url: str, data: Optional[Dict] = None, json_payload: Optional[Dict] = None,
             headers: Optional[Dict] = None) -> requests.Response:
        """POST请求 - 优化版"""
        response = self.session.post(
            url,
            data=data,
            json=json_payload,
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response
    
    def get(self, url: str, params: Optional[Dict] = None,
            headers: Optional[Dict] = None) -> requests.Response:
        """GET请求 - 优化版"""
        response = self.session.get(
            url,
            params=params,
            headers=headers,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response
    
    def close(self) -> None:
        """关闭会话"""
        self.session.close()
        logger.info("🔌 HTTP会话已关闭")


# 全局HTTP客户端实例 (线程安全单例)
http_client: Optional[HTTPClient] = None
_http_client_lock = threading.Lock()


def get_http_client(max_retries: Optional[int] = None, 
                    pool_size: Optional[int] = None, 
                    timeout: Optional[int] = None) -> HTTPClient:
    """获取线程安全单例HTTP客户端"""
    global http_client
    if http_client is None:
        with _http_client_lock:
            if http_client is None:
                http_client = HTTPClient(max_retries, pool_size, timeout)
    return http_client
