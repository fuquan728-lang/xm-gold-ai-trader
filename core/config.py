#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理 - V3.1 统一配置系统
统一管理所有配置和环境变量，支持热更新、配置验证和兼容性桥接

变更说明：
- 将根目录config.py的功能合并到core/config.py
- 支持运行时热更新（无需重启服务）
- 向后兼容旧的类变量访问方式
"""

import os
import threading
from pathlib import Path
from typing import List, Any, Dict, Callable, Optional
import dotenv


class Config:
    """
    全局配置管理 - 统一版
    
    特性：
    1. 实例模式：通过config.DEEPSEEK_API_KEY访问
    2. 模块级变量：通过core.config.DEEPSEEK_API_KEY访问（兼容旧代码）
    3. 热更新：调用reload()方法重新加载.env
    4. 变更通知：支持register_callback()注册配置变更回调
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._callbacks: Dict[str, List[Callable]] = {}
        self._warnings: List[str] = []
        self._load_env()
        self._set_defaults()
        self._validate_config()
    
    def _load_env(self):
        """加载环境变量"""
        # 查找.env文件
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            dotenv.load_dotenv(env_file)
            self._env_loaded = True
        else:
            self._env_loaded = False
        
        # DeepSeek配置
        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
        self.DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        self.USE_DEEPSEEK = os.getenv("USE_DEEPSEEK", "true").lower() == "true"
        self.ALLOW_FALLBACK_TRADING = os.getenv("ALLOW_FALLBACK_TRADING", "false").lower() == "true"
        
        # 性能配置
        self.REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
        self.CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", "10"))
        self.MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
        self.CACHE_SIZE = int(os.getenv("CACHE_SIZE", "100"))
        self.ENABLE_RL_MODEL = os.getenv("ENABLE_RL_MODEL", "false").lower() == "true"
        self.OBSERVATION_JOURNAL_ENABLED = os.getenv("OBSERVATION_JOURNAL_ENABLED", "true").lower() == "true"
        self.OBSERVATION_JOURNAL_DIR = os.getenv("OBSERVATION_JOURNAL_DIR", "logs/m5_observations")
        
        # 交易策略配置
        self.MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
        self.MIN_INDICATOR_SIGNALS = int(os.getenv("MIN_INDICATOR_SIGNALS", "3"))
        self.MIN_CONSISTENCY = float(os.getenv("MIN_CONSISTENCY", "0.7"))
        self.MAX_TRADE_SPREAD_PIPS = float(os.getenv("MAX_TRADE_SPREAD_PIPS", "3.0"))
        
        # 缓存配置
        self.CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"
        self.CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
        
        # 文件监控配置
        self.FILE_CHECK_INTERVAL = float(os.getenv("FILE_CHECK_INTERVAL", "0.05"))
        self.MAX_WAIT_RETRIES = int(os.getenv("MAX_WAIT_RETRIES", "100"))
        
        # 通信模式
        self.COMMUNICATION_MODE = os.getenv("COMMUNICATION_MODE", "auto")
        self.SOCKET_HOST = os.getenv("SOCKET_HOST", "127.0.0.1")
        self.SOCKET_PORT = int(os.getenv("SOCKET_PORT", "8080"))
        self.SOCKET_TIMEOUT = float(os.getenv("SOCKET_TIMEOUT", "5.0"))
        self.MAX_CONCURRENT_CONNECTIONS = int(os.getenv("MAX_CONCURRENT_CONNECTIONS", "10"))
        self.RETRY_BACKOFF_FACTOR = float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))
        self.FAILOVER_THRESHOLD = int(os.getenv("FAILOVER_THRESHOLD", "3"))
        self.AUTO_SWITCH_THRESHOLD = int(os.getenv("AUTO_SWITCH_THRESHOLD", "3"))
        
        # WebSocket配置 (已禁用以简化架构)
        self.WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", "8081"))
        self.WEBSOCKET_ENABLED = os.getenv("WEBSOCKET_ENABLED", "false").lower() == "true"
        
        # HTTP监控 (已禁用以简化架构)
        self.HTTP_PORT = int(os.getenv("HTTP_PORT", "8000"))
        self.HTTP_ENABLED = os.getenv("HTTP_ENABLED", "false").lower() == "true"
        
        # MQL5数据推送配置
        self.MQL5_DATA_PORT = int(os.getenv("MQL5_DATA_PORT", "8083"))
        self.MQL5_DATA_ENABLED = os.getenv("MQL5_DATA_ENABLED", "true").lower() == "true"
        
        # 文件模式路径
        self.FILE_MODE_PATH = os.getenv("FILE_MODE_PATH", "")
        self.MT5_PRIMARY_PATH = os.getenv("MT5_PRIMARY_PATH", "")
        
        # 风险管理配置
        self.MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.02"))
        self.MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))
        self.RISK_SCORE_THRESHOLD = float(os.getenv("RISK_SCORE_THRESHOLD", "0.8"))
        
        # 分层缓存配置
        self.L1_CACHE_SIZE = int(os.getenv("L1_CACHE_SIZE", "20"))
        self.L1_CACHE_TTL = int(os.getenv("L1_CACHE_TTL", "600"))
        self.L2_CACHE_SIZE = int(os.getenv("L2_CACHE_SIZE", "80"))
        self.L2_CACHE_TTL = int(os.getenv("L2_CACHE_TTL", "300"))
        self.L3_CACHE_SIZE = int(os.getenv("L3_CACHE_SIZE", "200"))
        self.L3_CACHE_TTL = int(os.getenv("L3_CACHE_TTL", "60"))
        
        # 金融数据集成配置
        self.FINANCE_DATA_ENABLED = os.getenv("FINANCE_DATA_ENABLED", "false").lower() == "true"
        self.NEODATA_ENABLED = os.getenv("NEODATA_ENABLED", "true").lower() == "true"
        self.MT5_QPI_ENABLED = os.getenv("MT5_QPI_ENABLED", "true").lower() == "true"
        self.EXTERNAL_DATA_SOURCES = os.getenv("EXTERNAL_DATA_SOURCES", "neodata,yahoo,mt5_qpi").split(",")
        self.MAX_EXTERNAL_RETRIES = int(os.getenv("MAX_EXTERNAL_RETRIES", "3"))
        self.NEODATA_TOKEN_PATH = os.path.expanduser("~/.workbuddy/.neodata_token")
        
        # 黄金交易特定配置
        self.GOLD_MIN_SPREAD = float(os.getenv("GOLD_MIN_SPREAD", "0.3"))
        self.GOLD_MAX_SPREAD = float(os.getenv("GOLD_MAX_SPREAD", "1.5"))
        self.DEFAULT_STOP_LOSS_PCT = float(os.getenv("DEFAULT_STOP_LOSS_PCT", "0.02"))
        self.DEFAULT_TAKE_PROFIT_PCT = float(os.getenv("DEFAULT_TAKE_PROFIT_PCT", "0.03"))
        self.RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "0.01"))
        self.MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", "5.0"))
        self.OVERNIGHT_FEE_FACTOR = float(os.getenv("OVERNIGHT_FEE_FACTOR", "1.5"))
        
        # MT5 QPI配置
        self.MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0"))
        self.MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
        self.MT5_SERVER = os.getenv("MT5_SERVER", "")
        self.MT5_QPI_AUTO_CONNECT = os.getenv("MT5_QPI_AUTO_CONNECT", "true").lower() == "true"
        
        # 数据缓存配置
        self.FINANCE_CACHE_TTL = int(os.getenv("FINANCE_CACHE_TTL", "300"))  # 5分钟
        self.MARKET_DATA_UPDATE_INTERVAL = int(os.getenv("MARKET_DATA_UPDATE_INTERVAL", "60"))  # 60秒
    
    def _set_defaults(self):
        """设置计算型默认值（依赖其他配置项的值）"""
        # 根据通信模式设置连接相关默认值
        if not hasattr(self, 'SOCKET_TIMEOUT') or self.SOCKET_TIMEOUT <= 0:
            self.SOCKET_TIMEOUT = 45.0
        
        if not hasattr(self, 'MAX_CONCURRENT_CONNECTIONS') or self.MAX_CONCURRENT_CONNECTIONS <= 0:
            self.MAX_CONCURRENT_CONNECTIONS = 10
        
        # 确保文件模式路径存在
        if hasattr(self, 'FILE_MODE_PATH') and self.FILE_MODE_PATH:
            import os as _os
            if not _os.path.exists(self.FILE_MODE_PATH):
                self._warnings.append(f"FILE_MODE_PATH does not exist: {self.FILE_MODE_PATH}")
        
        # 计算衍生配置
        self.RESPONSE_TIMEOUT_MS = int(self.SOCKET_TIMEOUT * 1000) if hasattr(self, 'SOCKET_TIMEOUT') else 45000
        self.FAILOVER_WINDOW_SEC = 60 * 5  # 5分钟故障转移窗口
    
    def _validate_config(self):
        """验证配置"""
        errors = []
        
        if self.REQUEST_TIMEOUT <= 0:
            errors.append(f"REQUEST_TIMEOUT必须>0，当前={self.REQUEST_TIMEOUT}")
        
        if self.CONNECTION_POOL_SIZE <= 0:
            errors.append(f"CONNECTION_POOL_SIZE必须>0，当前={self.CONNECTION_POOL_SIZE}")
        
        if self.MIN_CONFIDENCE < 0 or self.MIN_CONFIDENCE > 1:
            errors.append(f"MIN_CONFIDENCE必须在0-1之间，当前={self.MIN_CONFIDENCE}")
        
        if self.SOCKET_PORT < 1 or self.SOCKET_PORT > 65535:
            errors.append(f"SOCKET_PORT必须在1-65535之间，当前={self.SOCKET_PORT}")
        
        if self.WEBSOCKET_PORT < 1 or self.WEBSOCKET_PORT > 65535:
            errors.append(f"WEBSOCKET_PORT必须在1-65535之间，当前={self.WEBSOCKET_PORT}")
        
        if self.HTTP_PORT < 1 or self.HTTP_PORT > 65535:
            errors.append(f"HTTP_PORT必须在1-65535之间，当前={self.HTTP_PORT}")
        
        if self.MQL5_DATA_PORT < 1 or self.MQL5_DATA_PORT > 65535:
            errors.append(f"MQL5_DATA_PORT必须在1-65535之间，当前={self.MQL5_DATA_PORT}")
        
        if self.RISK_SCORE_THRESHOLD < 0 or self.RISK_SCORE_THRESHOLD > 1:
            errors.append(f"RISK_SCORE_THRESHOLD必须在0-1之间，当前={self.RISK_SCORE_THRESHOLD}")
        
        # 端口冲突检查
        ports = [self.SOCKET_PORT, self.WEBSOCKET_PORT, self.HTTP_PORT, self.MQL5_DATA_PORT]
        if len(ports) != len(set(ports)):
            errors.append(f"端口冲突: SOCKET({self.SOCKET_PORT}), WEBSOCKET({self.WEBSOCKET_PORT}), HTTP({self.HTTP_PORT}), MQL5_DATA({self.MQL5_DATA_PORT})")
        
        if errors:
            error_msg = "\n".join(errors)
            raise ValueError(f"配置验证失败:\n{error_msg}")
    
    def reload(self) -> Dict[str, Any]:
        """
        热更新配置：重新加载.env文件
        
        :return: 变更的配置项字典 {key: (old_value, new_value)}
        """
        with self._lock:
            # 保存旧值
            old_values = {
                key: getattr(self, key) for key in self._get_config_keys()
            }
            
            # 重新加载环境变量
            env_file = Path(__file__).parent.parent / ".env"
            if env_file.exists():
                dotenv.load_dotenv(env_file, override=True)
            
            # 重新加载配置
            self._load_env()
            self._validate_config()
            
            # 检测变更
            changes = {}
            for key in self._get_config_keys():
                new_val = getattr(self, key)
                if old_values.get(key) != new_val:
                    changes[key] = (old_values.get(key), new_val)
            
            # 更新模块级变量（保持兼容）
            self._sync_module_vars()
            
            # 触发回调
            for key, (old_val, new_val) in changes.items():
                self._notify_callbacks(key, old_val, new_val)
            
            return changes
    
    def register_callback(self, key: str, callback: Callable):
        """注册配置变更回调"""
        with self._lock:
            if key not in self._callbacks:
                self._callbacks[key] = []
            self._callbacks[key].append(callback)
    
    def _notify_callbacks(self, key: str, old_val: Any, new_val: Any):
        """通知配置变更回调"""
        if key in self._callbacks:
            for cb in self._callbacks[key]:
                try:
                    cb(key, old_val, new_val)
                except Exception as e:
                    # 回调异常不应影响配置系统
                    pass
    
    def _get_config_keys(self) -> List[str]:
        """获取所有配置键（排除内部属性）"""
        private_prefixes = ('_', 'env_loaded')
        return [
            key for key in vars(self)
            if not key.startswith(private_prefixes) and key.isupper()
        ]
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        兼容性方法：提供类似dict的get接口
        用于支持 self.config.get("ALPHA_VANTAGE_KEY", "") 等调用
        """
        return getattr(self, key, default)
    
    def _sync_module_vars(self):
        """同步模块级变量（保持向后兼容）"""
        global_vars = globals()
        for key in self._get_config_keys():
            global_vars[key] = getattr(self, key)
    
    def get_possible_paths(self) -> List[str]:
        """获取可能的MT5路径 - 完整版本"""
        base_paths = []
        
        if self.MT5_PRIMARY_PATH:
            base_paths.append(self.MT5_PRIMARY_PATH)
        
        # 嵌套目录结构（实际文件位置 - 最优先）
        project_root = Path(__file__).parent.parent
        base_paths.append(str(project_root / "MQL5" / "Files" / "MQL5" / "Files"))
        
        # 项目路径
        base_paths.append(str(project_root / "MQL5" / "Files"))
        base_paths.append(str(project_root))
        
        # 标准路径
        app_data = os.getenv("APPDATA")
        if app_data:
            base_paths.append(str(Path(app_data) / "MetaQuotes" / "Terminal" / "Common" / "Files"))
            base_paths.append(str(Path(app_data) / "MetaQuotes" / "Terminal" / "Files"))
            base_paths.append(str(Path(app_data) / "MetaQuotes" / "Terminal"))
        
        # 兼容旧路径（已移除硬编码路径，统一使用 project_root 和 MT5_PRIMARY_PATH 动态推导）
        
        return [p for p in base_paths if p]
    
    def get_summary(self) -> Dict[str, Any]:
        """获取配置摘要（脱敏）"""
        keys = self._get_config_keys()
        result = {}
        for key in keys:
            val = getattr(self, key)
            # 脱敏API密钥
            if 'KEY' in key and isinstance(val, str) and val:
                result[key] = f"{val[:6]}...{val[-4:]}" if len(val) > 10 else "***"
            else:
                result[key] = val
        return result


# ==================== 全局配置实例 ====================
config = Config()

# ==================== 模块级变量导出（兼容旧代码，通过 _sync_module_vars 保持同步） ====================
_EXPORTED_CONFIG_KEYS = [
    'DEEPSEEK_API_KEY', 'DEEPSEEK_API_URL', 'DEEPSEEK_MODEL', 'USE_DEEPSEEK',
    'ALLOW_FALLBACK_TRADING',
    'REQUEST_TIMEOUT', 'CONNECTION_POOL_SIZE', 'MAX_RETRIES', 'CACHE_SIZE', 'ENABLE_RL_MODEL',
    'OBSERVATION_JOURNAL_ENABLED', 'OBSERVATION_JOURNAL_DIR',
    'MIN_CONFIDENCE', 'MIN_INDICATOR_SIGNALS', 'MIN_CONSISTENCY', 'MAX_TRADE_SPREAD_PIPS',
    'COMMUNICATION_MODE', 'SOCKET_HOST', 'SOCKET_PORT', 'SOCKET_TIMEOUT',
    'MAX_CONCURRENT_CONNECTIONS', 'RETRY_BACKOFF_FACTOR', 'FAILOVER_THRESHOLD', 'AUTO_SWITCH_THRESHOLD',
    'FILE_MODE_PATH', 'MT5_PRIMARY_PATH', 'CACHE_ENABLED', 'FILE_CHECK_INTERVAL', 'MAX_WAIT_RETRIES',
    'WEBSOCKET_PORT', 'WEBSOCKET_ENABLED', 'HTTP_PORT', 'HTTP_ENABLED',
    'MQL5_DATA_PORT', 'MQL5_DATA_ENABLED',
    'MAX_DAILY_LOSS', 'MAX_POSITIONS', 'RISK_SCORE_THRESHOLD',
    'FINANCE_DATA_ENABLED', 'NEODATA_ENABLED', 'MT5_QPI_ENABLED',
    'GOLD_MIN_SPREAD', 'GOLD_MAX_SPREAD', 'DEFAULT_STOP_LOSS_PCT', 'DEFAULT_TAKE_PROFIT_PCT',
    'RISK_PER_TRADE_PCT', 'MAX_POSITION_SIZE', 'OVERNIGHT_FEE_FACTOR',
]

# 动态生成模块级变量（保持与 Config 实例同步）
for _key in _EXPORTED_CONFIG_KEYS:
    globals()[_key] = getattr(config, _key)


# ==================== 兼容性函数（供旧代码调用） ====================
def load_environment():
    """加载环境变量（兼容旧代码）"""
    return config


def validate():
    """验证配置（兼容旧代码）"""
    config._validate_config()


def get_possible_paths():
    """获取可能的路径（兼容旧代码）"""
    return config.get_possible_paths()


def reload_config():
    """热更新配置"""
    changes = config.reload()
    if changes:
        changed_keys = list(changes.keys())
        return f"已更新 {len(changes)} 项配置: {', '.join(changed_keys)}"
    return "配置无变化"


# 兼容性属性：供 mt5_ai_service.py 的 hasattr(config, 'config_loaded') 检查使用
config_loaded = True
