#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MT5 AI交易服务 - 企业级增强版 V3.0
提供 WebSocket/Socket/File/Auto 四种通信模式、完整监控系统、高性能架构
使用方法:
  python mt5_ai_service.py                      # 默认模式
  python mt5_ai_service.py --mode websocket     # 仅WebSocket模式
  python mt5_ai_service.py --mode socket        # 仅Socket模式
  python mt5_ai_service.py --mode file          # 仅File模式
  python mt5_ai_service.py --mode auto          # 自动模式(默认)
  python mt5_ai_service.py --log-file logs.log  # 同时输出到日志文件
"""

import sys
import time
import json
import signal
import argparse
import logging
import socket
import socketserver
import threading
import os
import asyncio
import traceback
import glob as _glob_module
from datetime import datetime
from typing import Dict, Any, Optional, Union, Tuple
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入核心模块
from core.logger import setup_logger, logger, monitor
from core.cache import global_cache, tiered_cache
from core.ai_engine import AIAnalyzer
from core.weight_optimizer import get_weight_optimizer, ValidationStatus
from core.file_handler import file_handler
from core.validator import DataValidator, IndicatorAnalyzer, get_cache_key, get_fuzzy_cache_key, get_cache_keys_for_lookup
from core.http_client import get_http_client
from core.websocket_handler import WebSocketHandler, HAS_WEBSOCKETS
from core.web_dashboard import WebDashboard
from core.ha import get_service_registry, create_local_service_instance, ServiceStatus
from core.trading_recorder import get_trading_recorder
from core.observation_journal import get_m5_observation_journal
from core.mql5_data import get_mql5_data_manager
from core.service.monitor import ServiceMonitor
from core.service.communication import (
    FileModeRunner, SocketModeRunner, WebSocketModeRunner,
    AISocketHandler, ThreadedTCPServer, parse_socket_payload,
)
from core.service.ai_coordinator import AIServiceCoordinator
from core.service.request_processor import RequestProcessor
from core.service.utils import (
    build_indicator_fingerprint, append_local_reason,
    utc_now_iso, latency_ms, total_latency_ms, derive_blocked_by,
    BLOCKING_RISK_KEYWORDS,
)
from core import config

try:
    from core.risk_manager import get_risk_manager, TradeRiskAssessment
    RISK_MANAGER_AVAILABLE = True
except ImportError as e:
    RISK_MANAGER_AVAILABLE = False
    logger.warning(f"[WARN]  风险管理器导入失败，将跳过风险评估: {e}")


# ==================== 全局状态 ====================
_service_status_lock = threading.Lock()

def _update_service_status(key: str, value):
    """线程安全的状态更新"""
    with _service_status_lock:
        service_status[key] = value

def _get_service_status(key: str, default=None):
    """线程安全的状态读取（简单类型无需加锁，字典修改需加锁）"""
    with _service_status_lock:
        return service_status.get(key, default)

service_status = {
    "running": True,
    "current_mode": "auto",
    "socket_available": False,
    "last_mode_switch": None,
    "consecutive_failures": 0,
    "start_time": datetime.now()
}

mode_manager_instance = None
PROTOCOL_VERSION = "v0.25.7"


# parse_socket_payload / AISocketHandler / ThreadedTCPServer
# 已迁移到 core/service/communication.py，通过 import 使用

# Phase 3 向后兼容性别名（旧函数名，无下划线版本从 utils 导入）
_total_latency_ms = total_latency_ms
_utc_now_iso = utc_now_iso
_latency_ms = latency_ms

# AISocketHandler / ThreadedTCPServer 已迁移到 core/service/communication.py

# ==================== 主服务类 ====================
class MT5AITradingService:
    """MT5 AI交易服务 - V3.0 企业级增强版"""
    
    def __init__(self):
        self.running = False
        self.ai_analyzer = AIAnalyzer()
        self.validator = DataValidator()
        self.indicator_analyzer = IndicatorAnalyzer()
        self.mode = "auto"
        
        # 通信 Runner（Phase 2 拆分，替代旧 socket_server/socket_thread/file_thread/websocket_handler/websocket_thread）
        self.socket_server = None   # 兼容性保留
        self.websocket_handler = None  # 兼容性保留
        
        self.web_dashboard = None
        
        # 权重优化器
        self.weight_optimizer = get_weight_optimizer()
        
        # 高可用架构
        self.service_registry = get_service_registry()
        self.local_instance = create_local_service_instance(
            port=8000,
            websocket_port=8081,
            socket_port=8080
        )
        
        # 交易记录器 - 为PPO强化学习准备
        self.trading_recorder = get_trading_recorder()
        self.observation_journal = get_m5_observation_journal(config.OBSERVATION_JOURNAL_DIR)
        
        # 服务监控模块 (Phase 1: ServiceMonitor)
        self.monitor = ServiceMonitor(
            service_registry=self.service_registry,
            local_instance=self.local_instance,
            file_handler=file_handler,
            web_dashboard=None,  # 在 run() 中设置
            observation_journal=self.observation_journal,
            current_mode_getter=lambda: _get_service_status("current_mode", "auto"),
        )
        
        # 通信模块 (Phase 2: Communication Runners)
        self.file_runner = FileModeRunner(
            process_request_func=self.process_request,
            file_handler=file_handler,
            local_instance=self.local_instance,
            observation_journal=self.observation_journal,
            running_getter=lambda: self.running,
        )
        self.socket_runner = SocketModeRunner(
            process_request_func=self.process_request,
            running_getter=lambda: self.running,
        )
        self.ws_runner = WebSocketModeRunner(
            process_request_func=self.process_request,
            running_getter=lambda: self.running,
        )
        
        # 风险管理器（可选，依赖numpy/scipy）
        self.risk_manager = None
        if RISK_MANAGER_AVAILABLE:
            try:
                self.risk_manager = get_risk_manager()
                self.risk_manager.start()
                logger.info("[OK] 风险管理器已集成并启动")
            except Exception as e:
                logger.warning(f"[WARN]  风险管理器启动失败，将跳过风险评估: {e}")
        
        # AI 分析协调器 (Phase 3: AICoordinator) — 必须在 risk_manager 之后创建
        self.coordinator = AIServiceCoordinator(
            ai_analyzer=self.ai_analyzer,
            risk_manager=self.risk_manager,
            indicator_analyzer=self.indicator_analyzer,
        )
        
        # 请求处理管道 (Phase 3: RequestProcessor)
        self.request_processor = RequestProcessor(
            ai_coordinator=self.coordinator,
            validator=self.validator,
            local_instance=self.local_instance,
            trading_recorder=self.trading_recorder,
            web_dashboard=None,  # 在 run() 中设置
            monitor_module=self.monitor,
        )
        
        # 只有主线程可以注册信号处理器
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except ValueError as e:
            if "signal only works in main thread" in str(e):
                logger.debug(f"[INFO] 非主线程，跳过信号处理器注册: {e}")
            else:
                raise
    
    def _signal_handler(self, signum, frame):
        logger.info("\n🔻 收到关闭信号，正在退出...")
        self.running = False
        self._cleanup()
        monitor.print_summary()
        logger.info("👋 再见！")
        sys.exit(0)
    
    def _cleanup(self):
        logger.info("🧹 正在清理资源...")
        # 停止监控模块
        self.monitor.running = False
        # 停止风险管理器
        if self.risk_manager:
            try:
                self.risk_manager.stop()
                logger.info("🛑 风险管理器已停止")
            except Exception as e:
                logger.warning(f"[WARN]  风险管理器停止异常: {e}")
        # 清理高可用架构
        try:
            self.service_registry.unregister(self.local_instance.service_id)
            logger.info("👋 服务注销完成")
        except Exception as e:
            logger.warning(f"[WARN]  服务注销异常: {e}")
        
        try:
            self.service_registry.stop()
        except Exception as e:
            logger.warning(f"[WARN]  服务注册中心停止异常: {e}")
        
        try:
            file_handler.cleanup_health_check()
        except Exception:
            pass
        try:
            http_client = get_http_client()
            http_client.close()
        except Exception:
            pass
        # 关闭通信 Runner (Phase 2)
        try:
            self.socket_runner.shutdown()
        except Exception:
            pass
        try:
            asyncio.run(self.ws_runner.stop())
        except Exception:
            pass
        logger.info("[OK] 清理完成")
    
    def _print_status(self, force: bool = False):
        """委托到 ServiceMonitor"""
        self.monitor.print_status(force=force)
    
    def _update_trade_stats(self, trade_history: list):
        """委托到 ServiceMonitor"""
        self.monitor.update_trade_stats(trade_history)
    
    def get_trade_stats(self) -> dict:
        """委托到 ServiceMonitor"""
        return self.monitor.get_trade_stats()
    
    def _calculate_dynamic_sl_tp(self, symbol: str, action: str, confidence: float,
                                  bid: float, ask: float, indicators: Optional[dict]) -> Tuple[int, int]:
        """委托到 AIServiceCoordinator（Phase 3）"""
        return self.coordinator.calculate_sl_tp(symbol, action, confidence, bid, ask, indicators)

    @staticmethod
    def _get_blocking_risk_reason(assessment) -> Optional[str]:
        """委托到 AIServiceCoordinator（Phase 3）"""
        return AIServiceCoordinator.get_blocking_risk_reason(assessment)
    
    def analyze(self, symbol: str, bid: float, ask: float,
                current_time: float, history: Optional[list] = None,
                indicators: Optional[dict] = None,
                multi_timeframe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """委托到 AIServiceCoordinator（Phase 3）"""
        return self.coordinator.analyze(
            symbol, bid, ask, current_time, history, indicators, multi_timeframe
        )
    
    # _heartbeat_loop 已迁移到 ServiceMonitor，由 run() 统一管理
    
    # _monitor_account_data 已迁移到 ServiceMonitor，由 run() 统一管理
    
    def process_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """委托到 RequestProcessor（Phase 3）"""
        return self.request_processor.process(request_data)
    
    def get_weight_optimizer_status(self) -> Dict[str, Any]:
        """获取权重优化器状态"""
        return self.weight_optimizer.get_performance_report()
    
    def trigger_weight_adjustment(self, reason: str = "manual") -> bool:
        """手动触发权重调整"""
        return self.weight_optimizer.adjust_weights(reason)
    
    def _start_socket_mode(self):
        """委托到 SocketModeRunner（Phase 2），保留兼容性"""
        self.socket_runner.start()
        _update_service_status("socket_available", True)
        # 保持兼容性引用
        self.socket_server = self.socket_runner.server
    
    def _run_socket_server(self):
        """已迁移到 SocketModeRunner（Phase 2）"""
        pass
    
    def _start_websocket_mode(self) -> bool:
        """委托到 WebSocketModeRunner（Phase 2），保留兼容性"""
        ok = self.ws_runner.start()
        # 保持兼容性引用
        self.websocket_handler = self.ws_runner.handler
        return ok
    
    def _run_file_mode(self):
        """委托到 FileModeRunner（Phase 2）"""
        self.file_runner.run()
    
    def run(self, mode: str = "auto"):
        self.running = True
        self.mode = mode
        _update_service_status("current_mode", mode)
        _update_service_status("start_time", datetime.now())
        
        # 启动高可用架构
        self.service_registry.start()
        self.service_registry.register(self.local_instance)
        logger.info(f"[OK] 高可用架构启动，服务ID: {self.local_instance.service_id}")
        
        # 启动监控模块（心跳 + 账户数据监控）
        self.monitor.running = True
        self.monitor.start_heartbeat()
        self.monitor.start_account_monitor()
        logger.info("[OK] 服务监控模块启动")
        
        print("\n" + "="*70)
        print("[TARGET] MT5 AI交易系统 - 企业级增强版 V3.0")
        print("="*70)
        print()
        print("[DATA] 配置信息:")
        print(f"  - 通信模式: {mode.upper()}")
        deepseek_status = self.ai_analyzer.get_deepseek_status()
        if deepseek_status == "启用":
            deepseek_prefix = "[OK]"
        elif deepseek_status == "禁用":
            deepseek_prefix = "[OFF]"
        else:
            deepseek_prefix = "[WARN]"
        print(f"  - DeepSeek: {deepseek_prefix} {deepseek_status}")
        print(f"  - 缓存大小: {config.CACHE_SIZE}")
        print(f"  - 置信度阈值: {config.MIN_CONFIDENCE}")
        print(f"  - 请求超时: {config.REQUEST_TIMEOUT}s")
        print(f"  - 服务ID: {self.local_instance.service_id}")
        
        if mode in ["websocket", "auto"]:
            print(f"  - WebSocket地址: ws://{config.SOCKET_HOST}:{config.SOCKET_PORT+1}")
        if mode in ["socket", "auto"]:
            print(f"  - Socket地址: {config.SOCKET_HOST}:{config.SOCKET_PORT}")
        
        print(f"  - Web Dashboard: http://127.0.0.1:8000")
        print()
        print("-> 服务已启动，等待请求...")
        print("="*70)
        print()
        
        # Start web dashboard
        self.web_dashboard = WebDashboard(host="127.0.0.1", port=8000)
        self.web_dashboard.start()
        self.monitor._web_dashboard = self.web_dashboard  # 同步到监控模块
        self.request_processor._web_dashboard = self.web_dashboard  # 同步到请求处理器
        
        self._print_status(force=True)
        published_ready = file_handler.publish_ready_to_known_paths(self.local_instance.service_id, mode)
        logger.info(f"[READY] service_ready.json published to {published_ready} path(s)")
        
        try:
            # File模式：只运行文件
            if mode == "file":
                self._run_file_mode()
            
            # Socket模式：只运行Socket
            elif mode == "socket":
                self._start_socket_mode()
                while self.running:
                    self._print_status()
                    time.sleep(0.1)
            
            # WebSocket模式：只运行WebSocket
            elif mode == "websocket":
                if not self._start_websocket_mode():
                    raise RuntimeError("WebSocket服务器启动失败")
                while self.running:
                    self._print_status()
                    time.sleep(0.1)
            
            # Auto模式：同时运行WebSocket/Socket和文件模式！
            else:
                websocket_running = False
                try:
                    websocket_running = self._start_websocket_mode()
                    if websocket_running:
                        logger.info("[OK] WebSocket模式启动成功")
                    else:
                        logger.warning("[WARN]  WebSocket模式未启动，继续使用Socket/文件模式")
                except Exception as e:
                    logger.warning(f"[WARN]  WebSocket模式启动失败: {e}")
                
                socket_running = False
                try:
                    self._start_socket_mode()
                    socket_running = True
                    logger.info("[OK] Socket模式启动成功")
                except Exception as e:
                    logger.warning(f"[WARN]  Socket模式启动失败: {e}")
                
                # 同时运行文件模式（主线程）
                self._run_file_mode()
        
        except KeyboardInterrupt:
            logger.info("\n👋 用户中断，正在退出...")
            monitor.print_summary()
        finally:
            self._cleanup()


# ==================== 全局函数 ====================
_ai_service_instance = None

def get_ai_service() -> MT5AITradingService:
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = MT5AITradingService()
    return _ai_service_instance


def main():
    parser = argparse.ArgumentParser(description="MT5 AI交易服务 - 企业级增强版 V3.0")
    parser.add_argument('--mode', type=str, default='auto', choices=['websocket', 'socket', 'file', 'auto'],
                        help='通信模式 (websocket/socket/file/auto，默认: auto)')
    parser.add_argument('--log-file', type=str, help='日志文件路径 (可选)')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志模式')
    args = parser.parse_args()
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    global logger
    logger = setup_logger(log_file=args.log_file, level=log_level)
    
    try:
        if hasattr(config, 'config'):
            # core/config.py 使用实例模式，配置已在导入时自动加载
            logger.info("[OK] 配置已通过模块导入自动加载")
        elif not hasattr(config, 'config_loaded'):
            # 根目录 config.py 使用类变量模式，需要手动加载
            if hasattr(config, 'load_environment'):
                config.load_environment()
            if hasattr(config, 'validate'):
                config.validate()
    except Exception as e:
        logger.error(f"[ERR] 配置加载失败: {e}")
        sys.exit(1)
    
    global _ai_service_instance
    _ai_service_instance = MT5AITradingService()
    _ai_service_instance.run(mode=args.mode)


if __name__ == "__main__":
    main()
