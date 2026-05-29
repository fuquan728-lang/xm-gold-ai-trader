#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置代理模块 - 向后兼容桥接

此文件为向后兼容保留，实际配置已统一到 core/config.py。
所有配置类、变量和函数均从 core.config 导入。

如需修改配置，请编辑：
  1. .env 文件（运行时配置）
  2. core/config.py（默认值和验证逻辑）
"""

from core.config import (
    Config,
    config,
    DEEPSEEK_API_KEY,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    USE_DEEPSEEK,
    REQUEST_TIMEOUT,
    CONNECTION_POOL_SIZE,
    MAX_RETRIES,
    CACHE_SIZE,
    MIN_CONFIDENCE,
    MIN_INDICATOR_SIGNALS,
    MIN_CONSISTENCY,
    COMMUNICATION_MODE,
    SOCKET_HOST,
    SOCKET_PORT,
    SOCKET_TIMEOUT,
    MAX_CONCURRENT_CONNECTIONS,
    RETRY_BACKOFF_FACTOR,
    FAILOVER_THRESHOLD,
    AUTO_SWITCH_THRESHOLD,
    FILE_MODE_PATH,
    MT5_PRIMARY_PATH,
    CACHE_ENABLED,
    FILE_CHECK_INTERVAL,
    MAX_WAIT_RETRIES,
    WEBSOCKET_PORT,
    WEBSOCKET_ENABLED,
    HTTP_PORT,
    HTTP_ENABLED,
    MAX_DAILY_LOSS,
    MAX_POSITIONS,
    RISK_SCORE_THRESHOLD,
    load_environment,
    validate,
    get_possible_paths,
    reload_config,
    config_loaded,
)


# 保持旧代码中 Config 类的静态方法兼容
# 旧代码可能通过 Config.validate() 或 Config.get_possible_paths() 调用
_config_get_possible_paths = Config.get_possible_paths

Config.validate = classmethod(lambda cls: config._validate_config())
Config.get_possible_paths = staticmethod(lambda: _config_get_possible_paths(config))
