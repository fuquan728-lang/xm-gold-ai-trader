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


_INDICATOR_FINGERPRINT_KEYS = ("rsi", "macd_main", "macd_signal", "ema50", "atr")


def build_indicator_fingerprint(indicators: Optional[Dict[str, Any]]) -> Optional[str]:
    """Build a compact fingerprint so cached signals cannot cross indicator states."""
    if not indicators:
        return None

    parts = []
    for key in _INDICATOR_FINGERPRINT_KEYS:
        if key not in indicators:
            continue
        try:
            parts.append(f"{key}:{float(indicators[key]):.4f}")
        except (TypeError, ValueError):
            parts.append(f"{key}:{indicators[key]}")
    return "|".join(parts) if parts else None


def append_local_reason(ai_reason: str, local_reason: str) -> str:
    if not local_reason:
        return ai_reason
    if not ai_reason:
        return f"本地指标校验: {local_reason}"
    combined = f"{ai_reason} | 本地指标校验: {local_reason}"
    return combined[:240]


def _utc_now_iso() -> str:
    return datetime.now().isoformat()


def _latency_ms(start_iso: Optional[str], end_iso: Optional[str] = None) -> Optional[int]:
    if not start_iso:
        return None
    try:
        start = datetime.fromisoformat(str(start_iso))
        end = datetime.fromisoformat(str(end_iso)) if end_iso else datetime.now()
        return max(0, int((end - start).total_seconds() * 1000))
    except Exception:
        return None


def _total_latency_ms(request_created_at: Optional[str], request_read_at: Optional[str], end_iso: str) -> Optional[int]:
    read_latency = _latency_ms(request_read_at, end_iso)
    created_latency = _latency_ms(request_created_at, end_iso)
    if read_latency is None:
        return created_latency
    if created_latency is None:
        return read_latency
    if created_latency > read_latency + 300_000:
        return read_latency
    return created_latency


def _build_protocol_response(
    payload: Dict[str, Any],
    request_id: str = "",
    response_matched: Optional[bool] = None,
    stale_response: Optional[bool] = False,
) -> Dict[str, Any]:
    response: Dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": str(request_id or ""),
    }
    for key, value in payload.items():
        if key in ("protocol_version", "request_id"):
            continue
        response[key] = value
    response.setdefault("stale_response_guard", True)
    response.setdefault("request_id_required", True)
    if response_matched is not None:
        response["response_matched"] = bool(response_matched)
    if stale_response is not None:
        response["stale_response"] = bool(stale_response)
    return response


def _derive_blocked_by(result: Dict[str, Any]) -> list:
    blocked = []
    if not isinstance(result, dict):
        return blocked

    if result.get("action") != "HOLD":
        return blocked

    blocked.append("ACTION_HOLD")
    reason = str(result.get("reason", ""))
    validation = result.get("indicator_validation")
    if isinstance(validation, dict):
        blocks = validation.get("blocks") or []
        if any("pips>" in str(block) for block in blocks):
            blocked.append("SPREAD_TOO_HIGH")
        if validation.get("original_action") in ("BUY", "SELL") and validation.get("adjusted"):
            blocked.append("INDICATOR_QUALITY_GATE")

    confidence = result.get("original_confidence", result.get("confidence", 0.0))
    try:
        if float(confidence) < float(config.MIN_CONFIDENCE):
            blocked.append("LOW_CONFIDENCE")
    except Exception:
        pass

    if "DeepSeek" in reason or "AI" in reason:
        if "不可用" in reason or "失败" in reason or "disabled" in reason.lower():
            blocked.append("AI_UNAVAILABLE")
    if result.get("risk_downgrade_reason"):
        blocked.append("RISK_DOWNGRADE")

    return list(dict.fromkeys(blocked))

# 阻断性风险关键词（模块级常量，避免重复构造）
_BLOCKING_RISK_KEYWORDS = (
    "保证金不足", "无法开仓", "保证金追缴", "立即平仓",
    "账户不允许", "交易被禁用", "风险评估失败",
    "margin insufficient", "not enough margin",
)


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
        """
        动态计算止损止盈 pips 数
        
        ★ 单位约定（与EA端保持一致）：
            1 pip = 10 * _Point（MT5 黄金 _Point=0.01）
            即 1 pip = 0.10 美元
            30 pip = 3.00 美元，60 pip = 6.00 美元
        
        MT5 stops_level 通常 100-200 points = 10-20 pips
        → 止损最小值设 25 pips (2.50$)，避免 [invalid stops]
        
        基于以下因素调整：
        1. 市场波动率（ATR）
        2. 置信度
        3. 账户风险状态
        4. 品种特性（黄金vs外汇）
        
        返回: (stop_loss_pips, take_profit_pips)
        """
        # 基础止损止盈（外汇默认范围，单位: pips）
        base_sl = 30  # 30 pips = 3.00$ (外汇约30点)
        base_tp = 60  # 60 pips = 6.00$
        
        # 黄金/贵金属特殊处理（波动大，需要更宽止损）
        # 检测逻辑：XAU前缀、GOLD关键词、或以_结尾的MT5黄金品种（如GOLD_）
        sym_upper = symbol.upper()
        is_gold = (sym_upper.startswith("XAU") or 
                   "GOLD" in sym_upper or 
                   sym_upper.endswith("_"))  # MT5黄金品种惯例以_结尾
        if is_gold:
            # 黄金 stops_level 通常 100-300 points = 10-30 pips
            # 设 40 pips (4.00$) 确保超过最小距离
            base_sl = 40  # 40 pips = 4.00$
            base_tp = 80  # 80 pips = 8.00$，风险回报比 2:1
            logger.debug(f"[SL/TP] 黄金品种({symbol})，使用宽止损: SL={base_sl}pips(${base_sl*0.1:.1f}), TP={base_tp}pips(${base_tp*0.1:.1f})")
        
        # 从指标计算波动率
        volatility_multiplier = 1.0
        if indicators:
            # 使用RSI作为波动率参考
            rsi = indicators.get('rsi', 50)
            if rsi > 70 or rsi < 30:
                volatility_multiplier = 1.3  # 超买超卖区域波动大
            
            # 使用历史数据计算波动（ATR近似）
            history = indicators.get('recent_history', [])
            if len(history) >= 5:
                highs = [h.get('high', 0) for h in history]
                lows = [h.get('low', 0) for h in history]
                closes = [h.get('close', 0) for h in history]
                
                # 计算ATR近似（单位: 价格）
                true_ranges = []
                for i in range(1, len(closes)):
                    tr = max(
                        highs[i] - lows[i],
                        abs(highs[i] - closes[i-1]),
                        abs(lows[i] - closes[i-1])
                    )
                    true_ranges.append(tr)
                
                if true_ranges:
                    avg_atr = sum(true_ranges) / len(true_ranges)
                    # ATR单位：价格（如黄金3300价格，ATR=5.0表示5.00美元波动）
                    # 转换为pips：1 pip = 0.10$（MT5黄金_Point=0.01）
                    # ATR > 5.0$ = 50 pips → 高波动 → volatility_multiplier = 1.3
                    # ATR < 2.0$ = 20 pips → 低波动 → volatility_multiplier = 0.85
                    if avg_atr > 5.0:
                        volatility_multiplier = 1.3
                    elif avg_atr < 2.0:
                        volatility_multiplier = 0.85
        
        # 置信度调整（高置信度适当放宽止盈，低置信度收紧止损但保持盈亏比）
        if confidence < 0.65:
            # 边缘信号：大幅收紧SL和TP，保持最小1.5:1盈亏比
            sl_multiplier = 0.75
            tp_multiplier = 0.85  # 止盈也收紧，但盈亏比保持
        elif confidence < 0.70:
            # 偏弱信号：适度收紧
            sl_multiplier = 0.85
            tp_multiplier = 0.90
        elif confidence > 0.85:
            # 高置信度：适当放宽TP追求更大盈利
            sl_multiplier = 1.0
            tp_multiplier = 1.2
        else:
            # 中等置信度：标准倍数
            sl_multiplier = 1.0
            tp_multiplier = 1.0
        
        # 风险管理器调整
        risk_adjustment = 1.0
        if self.risk_manager:
            try:
                risk_level = self.risk_manager.risk_params.risk_level
                if hasattr(risk_level, 'value'):
                    if 'high' in risk_level.value.lower():
                        risk_adjustment = 0.7  # 高风险时收紧止损
                        logger.debug(f"[SL/TP] 高风险状态，止损收紧 x{risk_adjustment}")
                    elif 'low' in risk_level.value.lower():
                        risk_adjustment = 1.1  # 低风险时放宽
                        logger.debug(f"[SL/TP] 低风险状态，止损放宽 x{risk_adjustment}")
            except Exception as e:
                logger.debug(f"[SL/TP] 风险等级读取失败，使用默认倍数: {e}")
        
        # 计算最终止损止盈（分别使用SL和TP的调整系数）
        final_sl_multiplier = volatility_multiplier * sl_multiplier * risk_adjustment
        final_tp_multiplier = volatility_multiplier * tp_multiplier * risk_adjustment
        
        stop_loss_pips = int(base_sl * final_sl_multiplier)
        take_profit_pips = int(base_tp * final_tp_multiplier)
        
        # 确保风险回报比至少1.5:1
        if take_profit_pips < stop_loss_pips * 1.5:
            take_profit_pips = int(stop_loss_pips * 1.5)
        
        # 范围限制（单位: pips，1pip=0.10$）
        # SL最小25pips(2.50$)，确保超过MT5 stops_level(通常100-300 points=10-30pips)
        stop_loss_pips = max(25, min(150, stop_loss_pips))
        take_profit_pips = max(40, min(300, take_profit_pips))
        
        logger.debug(f"[SL/TP] 最终计算: SL={stop_loss_pips}pips(${stop_loss_pips*0.1:.1f}) "
                     f"TP={take_profit_pips}pips(${take_profit_pips*0.1:.1f}) "
                     f"SL乘数={final_sl_multiplier:.2f}, TP乘数={final_tp_multiplier:.2f}")
        
        return stop_loss_pips, take_profit_pips

    @staticmethod
    def _get_blocking_risk_reason(assessment) -> Optional[str]:
        """返回阻断交易的风险原因；无阻断风险则返回None。"""
        warnings = getattr(assessment, "warning_messages", None) or []

        for warning in warnings:
            warning_text = str(warning)
            if any(keyword.lower() in warning_text.lower() for keyword in _BLOCKING_RISK_KEYWORDS):
                return warning_text

        position_size = getattr(assessment, "recommended_position_size", None)
        if position_size is not None and position_size <= 0:
            return "推荐仓位为0，禁止开仓"

        risk_reward_ratio = getattr(assessment, "risk_reward_ratio", None)
        if risk_reward_ratio is not None and risk_reward_ratio <= 0:
            return f"风险回报比{risk_reward_ratio:.2f}无效，禁止开仓"

        return None
    
    def analyze(self, symbol: str, bid: float, ask: float,
                current_time: float, history: Optional[list] = None,
                indicators: Optional[dict] = None,
                multi_timeframe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        start_time = time.time()
        allow_fallback_trading = bool(getattr(config, "ALLOW_FALLBACK_TRADING", False))
        indicator_fingerprint = build_indicator_fingerprint(indicators)

        def unavailable_ai_hold(reason: str) -> Dict[str, Any]:
            monitor.record_request(True, time.time() - start_time)
            return {
                "action": "HOLD",
                "confidence": 0.75,
                "reason": reason,
                "symbol": symbol,
                "analysis_time": datetime.now().isoformat(),
                "use_deepseek": False,
                "cached": False,
            }
        
        # 尝试多个缓存键（精确键 + 模糊键）
        cache_keys = get_cache_keys_for_lookup(symbol, bid, ask)
        cached_result = None
        used_cache_key = None
        
        for cache_key in cache_keys:
            cached = global_cache.get(cache_key)
            if cached:
                if not isinstance(cached, dict):
                    logger.info(f"[CACHE] Skipping invalid cached result type: {type(cached).__name__}")
                    continue
                cached_action = cached.get("action") if isinstance(cached, dict) else None
                if not allow_fallback_trading and cached_action in ("BUY", "SELL"):
                    logger.info(f"[CACHE] Safe mode skips cached trade signal {cached_action}: {cache_key}")
                    continue
                cached_fingerprint = cached.get("indicator_fingerprint") if isinstance(cached, dict) else None
                if indicator_fingerprint and cached_fingerprint != indicator_fingerprint:
                    logger.info(f"[CACHE] 指标快照变化，跳过缓存结果: {cache_key}")
                    continue
                cached_result = cached
                used_cache_key = cache_key
                break
        
        if cached_result:
            is_exact_match = used_cache_key == cache_keys[0]  # 第一个键是精确键
            logger.info(f"💾 使用{'精确' if is_exact_match else '模糊'}缓存结果 (键: {used_cache_key})")
            monitor.record_cache_hit()
            if (
                not allow_fallback_trading
                and not self.ai_analyzer.is_deepseek_available()
                and cached_result.get("action") in ("BUY", "SELL")
            ):
                return unavailable_ai_hold("AI不可用且后备交易未启用，缓存交易信号降级为HOLD")
            return cached_result
        
        monitor.record_cache_miss()
        
        action = "HOLD"
        confidence = 0.5
        reason = ""
        
        # 用于存储动态止损止盈
        stop_loss_pips = None
        take_profit_pips = None
        
        deepseek_used = False
        if self.ai_analyzer.is_deepseek_available():
            prompt = self.ai_analyzer.build_prompt(symbol, bid, ask, current_time, history, indicators, multi_timeframe)
            ai_result = self.ai_analyzer.call_api(prompt)
            
            if ai_result:
                deepseek_used = True
                action = ai_result["action"]
                confidence = ai_result["confidence"]
                reason = ai_result["reason"]
                # 从AI结果中提取止损止盈
                stop_loss_pips = ai_result.get("stop_loss_pips")
                take_profit_pips = ai_result.get("take_profit_pips")
                monitor.record_request(True, time.time() - start_time)
            else:
                if not allow_fallback_trading:
                    logger.warning("[SAFE] AI分析失败，后备交易未启用，返回HOLD")
                    return unavailable_ai_hold("AI分析失败，后备交易未启用")
                logger.warning("[WARN]  AI分析失败，使用后备策略")
                action, confidence, reason = self.ai_analyzer.get_fallback_strategy(
                    symbol, bid, ask, indicators, multi_timeframe
                )
                monitor.record_request(True, time.time() - start_time)
        else:
            if not allow_fallback_trading:
                if self.ai_analyzer.use_deepseek:
                    logger.warning("[SAFE] DeepSeek不可用，后备交易未启用，返回HOLD")
                    return unavailable_ai_hold("DeepSeek不可用，后备交易未启用")
                logger.info("[SAFE] DeepSeek已禁用，后备交易未启用，返回HOLD")
                return unavailable_ai_hold("DeepSeek已禁用，后备交易未启用")
            action, confidence, reason = self.ai_analyzer.get_fallback_strategy(
                symbol, bid, ask, indicators, multi_timeframe
            )
            monitor.record_request(True, time.time() - start_time)

        indicator_validation = self.indicator_analyzer.evaluate_signal(
            action, confidence, indicators, symbol, bid, ask
        )
        action = indicator_validation["action"]
        confidence = indicator_validation["confidence"]
        reason = append_local_reason(reason, indicator_validation.get("reason", ""))
        
        # RL模型后备: AI决策为HOLD时, 尝试RL模型给出备选信号
        if action == "HOLD" and indicators and isinstance(indicators, dict) and getattr(config, "ENABLE_RL_MODEL", False):
            try:
                from core.rl_inference import get_rl_signal
                rl_action, rl_conf, rl_reason = get_rl_signal(indicators, bid, ask)
                if rl_action != "HOLD" and rl_conf > 0.55:
                    logger.info(f"[RL] RL后备信号: {rl_action} conf={rl_conf:.2f}")
                    reason = reason + " | RL备选: " + rl_reason[:60]
                    # 注意: RL信号仅记录不覆盖AI决策, 保持AI为主
            except Exception as e:
                logger.debug(f"[RL] RL后备检查跳过: {e}")
        
        if action == "HOLD":
            stop_loss_pips = None
            take_profit_pips = None
        
        # 计算动态止损止盈（如果AI没有提供）
        if action in ['BUY', 'SELL'] and (stop_loss_pips is None or take_profit_pips is None):
            # 基于波动率计算
            sl, tp = self._calculate_dynamic_sl_tp(symbol, action, confidence, bid, ask, indicators)
            if stop_loss_pips is None:
                stop_loss_pips = sl
            if take_profit_pips is None:
                take_profit_pips = tp
        
        result = {
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "symbol": symbol,
            "analysis_time": datetime.now().isoformat(),
            "use_deepseek": deepseek_used,
            "cached": False,
            "indicator_validation": indicator_validation,
            "indicator_fingerprint": indicator_fingerprint
        }
        
        # 添加动态止损止盈到结果（仅对交易信号）
        if action in ['BUY', 'SELL']:
            if stop_loss_pips is not None:
                result["stop_loss_pips"] = stop_loss_pips
            if take_profit_pips is not None:
                result["take_profit_pips"] = take_profit_pips
            logger.info(f"📊 动态止损止盈: SL={stop_loss_pips}点, TP={take_profit_pips}点")

        def downgrade_to_hold(downgrade_reason: str):
            result["original_action"] = result.get("action")
            result["original_confidence"] = result.get("confidence")
            result["original_reason"] = result.get("reason")
            result["action"] = "HOLD"
            result["confidence"] = 0.0
            result["reason"] = f"风险拦截: {downgrade_reason}"
            result["risk_downgrade_reason"] = downgrade_reason
            result.pop("stop_loss_pips", None)
            result.pop("take_profit_pips", None)
        
        # 风险评估：对交易信号进行多维度风险检查
        if action in ['BUY', 'SELL']:
            if not self.risk_manager:
                logger.warning("[RM] 风险管理器不可用，信号降级为HOLD")
                downgrade_to_hold("风险管理器不可用")
            else:
                try:
                    current_price = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
                    if current_price <= 0:
                        logger.warning("[RM] 当前价格无效，信号降级为HOLD")
                        downgrade_to_hold("当前价格无效")
                    else:
                        # --- 多维度风险预检（不依赖assess_trade_risk） ---
                        spread = ask - bid if bid > 0 and ask > 0 else 0
                        spread_pct = (spread / current_price * 10000) if current_price > 0 else 0
                        
                        # 维度1: 点差异常检查（流动性不足）
                        if spread_pct > 50:  # 点差超过5个标准点
                            logger.warning(f"[RM]  点差异常({spread_pct:.1f}点)，流动性不足，信号降级为HOLD")
                            downgrade_to_hold(f"点差异常: {spread_pct:.1f}点，流动性不足")
                        else:
                            # 维度2: 完整风险评估
                            assessment = self.risk_manager.assess_trade_risk(
                                symbol=symbol,
                                action=action,
                                confidence=confidence,
                                current_price=current_price
                            )
                            # 将风险评估信息附加到结果中
                            result["risk_assessment"] = {
                                "risk_score": assessment.risk_score,
                                "risk_level": assessment.risk_level.value,
                                "recommended_position_size": assessment.recommended_position_size,
                                "recommended_stop_loss": assessment.recommended_stop_loss,
                                "recommended_take_profit": assessment.recommended_take_profit,
                                "risk_reward_ratio": assessment.risk_reward_ratio,
                                "warnings": assessment.warning_messages
                            }
                            
                            # 多维度降级逻辑
                            risk_reasons = []
                            blocking_risk_reason = self._get_blocking_risk_reason(assessment)
                            
                            # 维度2a: 风险评分过高
                            if assessment.risk_score >= 0.8:
                                risk_reasons.append(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            
                            # 维度2b: 风险回报比不足
                            if assessment.risk_reward_ratio < 1.0:
                                risk_reasons.append(f"风险回报比{assessment.risk_reward_ratio:.2f}低于1:1")
                            
                            # 维度2c: 置信度与风险评分不匹配
                            if confidence < 0.6 and assessment.risk_score > 0.5:
                                risk_reasons.append(f"低置信度({confidence:.2f})+高风险({assessment.risk_score:.2f})")
                            
                            # 根据风险原因数量决定处理方式
                            if blocking_risk_reason:
                                logger.warning(f"[RM]  阻断性风险触发({blocking_risk_reason})，信号降级为HOLD")
                                downgrade_to_hold(f"阻断性风险: {blocking_risk_reason}")
                            elif len(risk_reasons) >= 2:
                                logger.warning(f"[RM]  多维度风险触发(原因: {'; '.join(risk_reasons)})，信号降级为HOLD")
                                downgrade_to_hold(f"多维度风险: {'; '.join(risk_reasons)}")
                            elif assessment.risk_score >= 0.8:
                                logger.warning(f"[RM]  风险评分过高({assessment.risk_score:.2f})，信号降级为HOLD")
                                downgrade_to_hold(f"风险评分{assessment.risk_score:.2f}超过阈值0.8")
                            elif assessment.risk_score > 0.6:
                                logger.warning(f"[WARN]  风险评分偏高({assessment.risk_score:.2f})，保留信号但添加警告")
                                result["risk_warnings"] = risk_reasons
                except Exception as e:
                    logger.error(f"[RM] 风险评估异常，信号降级为HOLD: {e}")
                    downgrade_to_hold(f"风险评估异常: {str(e)[:120]}")
        
        # 存储到多个缓存键以提高命中率
        primary_cache_key = get_cache_key(symbol, bid, ask)  # 精确键
        global_cache.set(primary_cache_key, result)
        
        # 同时存储到主要模糊键（0.5点容忍度）
        fuzzy_cache_key = get_fuzzy_cache_key(symbol, bid, ask, tolerance_pips=0.5)
        if fuzzy_cache_key != primary_cache_key:
            global_cache.set(fuzzy_cache_key, result)
        
        logger.info(f"[AI] AI建议: {result.get('action', action)} | 置信度: {result.get('confidence', confidence):.2f}")
        if reason:
            logger.info(f"💭 分析原因: {reason[:80]}{'...' if len(reason) > 80 else ''}")
        
        return result
    
    # _heartbeat_loop 已迁移到 ServiceMonitor，由 run() 统一管理
    
    # _monitor_account_data 已迁移到 ServiceMonitor，由 run() 统一管理
    
    def process_request(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            # 高可用架构统计
            self.local_instance.increment_requests()

            if not isinstance(request_data, dict):
                raise ValueError("请求数据必须是JSON对象")

            if request_data.get("type") == "mql5_data":
                mql5_manager = get_mql5_data_manager()
                success = mql5_manager.update_from_json(request_data)
                return _build_protocol_response({
                    "status": "ok" if success else "error",
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "MQL5数据更新" if success else "MQL5数据更新失败",
                    "use_deepseek": False,
                    "cached": False
                }, str(request_data.get("request_id", "")), response_matched=bool(request_data.get("request_id")))

            request_id = str(request_data.get("request_id", "")).strip()
            request_created_at = request_data.get("request_created_at") or request_data.get("timestamp")
            request_read_at = request_data.get("_request_read_at") or _utc_now_iso()
            ea_timeout_seconds = request_data.get("ea_timeout_seconds")
            if not request_id:
                return _build_protocol_response({
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": "Missing request_id; request ignored for stale-response safety",
                    "symbol": str(request_data.get("symbol", "UNKNOWN")),
                    "analysis_time": _utc_now_iso(),
                    "use_deepseek": False,
                    "cached": False,
                    "request_created_at": request_created_at,
                    "request_read_at": request_read_at,
                    "ai_started_at": None,
                    "ai_finished_at": None,
                    "latency_total_ms": _total_latency_ms(request_created_at, request_read_at, _utc_now_iso()),
                    "latency_ai_ms": None,
                    "response_matched": False,
                    "stale_response": False,
                    "ea_timeout_seconds": ea_timeout_seconds,
                    "blocked_by": ["MISSING_REQUEST_ID"],
                }, "", response_matched=False, stale_response=False)
            
            validated_request = dict(request_data)
            try:
                validated_request["bid"] = float(validated_request.get("bid"))
                validated_request["ask"] = float(validated_request.get("ask"))
                validated_request["time"] = float(validated_request.get("time", int(time.time())))
                self.validator.validate_request(validated_request)
            except Exception as validation_error:
                logger.warning(f"[SAFE] 请求校验失败，返回HOLD: {validation_error}")
                return _build_protocol_response({
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": f"请求校验失败: {validation_error}",
                    "symbol": str(request_data.get("symbol", "UNKNOWN")),
                    "analysis_time": _utc_now_iso(),
                    "use_deepseek": False,
                    "cached": False,
                    "request_created_at": request_created_at,
                    "request_read_at": request_read_at,
                    "ai_started_at": None,
                    "ai_finished_at": None,
                    "latency_total_ms": _total_latency_ms(request_created_at, request_read_at, _utc_now_iso()),
                    "latency_ai_ms": None,
                    "response_matched": True,
                    "stale_response": False,
                    "ea_timeout_seconds": ea_timeout_seconds,
                    "blocked_by": ["REQUEST_VALIDATION_FAILED"],
                }, request_id, response_matched=True, stale_response=False)

            symbol = validated_request["symbol"].strip()
            bid = validated_request["bid"]
            ask = validated_request["ask"]
            current_time = validated_request["time"]
            history = request_data.get("history")
            indicators = request_data.get("indicators")
            
            # 兼容EA的扁平JSON格式: 顶层rsi/macd_main/macd_signal/ema50 → 嵌套indicators
            if not isinstance(indicators, dict):
                flat_indicators = {}
                for key in ("rsi", "macd_main", "macd_signal", "ema50", "atr", "stochastic_k", "stochastic_d"):
                    if key in request_data and request_data[key] is not None:
                        flat_indicators[key] = request_data[key]
                if flat_indicators:
                    indicators = flat_indicators
                    logger.debug(f"[DATA] 从EA扁平JSON提取指标: {list(flat_indicators.keys())}")
            multi_timeframe = request_data.get("multi_timeframe")
            account_data = request_data.get("account_data")  # 从请求中获取账户数据
            trade_history = request_data.get("trade_history", [])  # 交易历史数据
            
            # 更新MQL5数据管理器中的账户信息
            if isinstance(account_data, dict):
                mql5_manager = get_mql5_data_manager()
                balance = account_data.get("balance", 0.0)
                equity = account_data.get("equity", 0.0)
                margin_free = account_data.get("margin_free", 0.0)
                margin = account_data.get("margin", 0.0)
                margin_level = account_data.get("margin_level", 0.0)
                if margin <= 0 and (margin_free > 0 or equity > 0) and margin_level <= 0:
                    margin_level = 1000.0

                mql5_manager.account_info.balance = balance
                mql5_manager.account_info.equity = equity
                mql5_manager.account_info.margin_free = margin_free
                mql5_manager.account_info.margin = margin
                mql5_manager.account_info.margin_level = margin_level
                mql5_manager.account_info.profit = account_data.get("profit", 0.0)
                logger.debug(f"[DATA] 账户数据已更新: 净值={account_data.get('equity', 0):.2f}")
            
            # 更新交易历史数据并统计准确率
            if isinstance(trade_history, list) and trade_history:
                self._update_trade_stats(trade_history)
            
            logger.info(f"📥 收到请求: {symbol} Bid={bid} Ask={ask}")
            ai_started_at = _utc_now_iso()
            result = self.analyze(symbol, bid, ask, current_time, history, indicators, multi_timeframe)
            ai_finished_at = _utc_now_iso()
            if result:
                payload = dict(result)
                payload["request_created_at"] = request_created_at
                payload["request_read_at"] = request_read_at
                payload["ai_started_at"] = ai_started_at
                payload["ai_finished_at"] = ai_finished_at
                payload["latency_ai_ms"] = _latency_ms(ai_started_at, ai_finished_at)
                payload["latency_total_ms"] = _total_latency_ms(request_created_at, request_read_at, ai_finished_at)
                payload["response_matched"] = True
                payload["stale_response"] = False
                payload["ea_timeout_seconds"] = ea_timeout_seconds
                payload["blocked_by"] = _derive_blocked_by(payload)
                result = _build_protocol_response(payload, request_id, response_matched=True, stale_response=False)
            
            # Add to dashboard
            if result and self.web_dashboard:
                self.web_dashboard.add_signal(result)
                self.web_dashboard.record_request(True)
            
            # 记录AI分析 - 为PPO强化学习准备
            if result:
                action = result.get('action', 'HOLD')
                confidence = result.get('confidence', 0)
                
                self.trading_recorder.record_analysis(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    action=action,
                    confidence=confidence,
                    reason=result.get('reason', ''),
                    use_deepseek=result.get('use_deepseek', False),
                    cached=result.get('cached', False),
                    indicators=indicators,
                    history=history
                )
                
                # 如果是交易信号，记录开仓信息（等待实盘平仓后更新）
                if action in ['BUY', 'SELL'] and confidence > 0.5:
                    entry_price = ask if action == 'BUY' else bid
                    
                    trade_data = {
                        'symbol': symbol,
                        'action': action,
                        'entry_price': entry_price,
                        'exit_price': None,  # 等待实盘平仓后填入
                        'pnl': None,          # 等待实盘平仓后计算
                        'status': 'open',     # 标记为待平仓状态
                        'confidence': confidence,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    if self.web_dashboard:
                        self.web_dashboard.add_trade(trade_data)
                    
                    logger.info(f"[LOG] 记录开仓信号: {action} {symbol} @ {entry_price:.5f}")
            
            return result
        
        except Exception as e:
            logger.error(f"[ERR] 处理请求失败: {e}")
            logger.error(f"   堆栈: {traceback.format_exc()}")
            monitor.record_request(False, 0)
            if self.web_dashboard:
                self.web_dashboard.record_request(False)
            request_id = str(request_data.get("request_id", "")) if isinstance(request_data, dict) else ""
            return _build_protocol_response({
                "action": "HOLD",
                "confidence": 0.0,
                "reason": f"处理请求异常: {str(e)}",
                "analysis_time": _utc_now_iso(),
                "use_deepseek": False,
                "cached": False,
                "response_matched": bool(isinstance(request_data, dict) and request_data.get("request_id")),
                "stale_response": False,
                "blocked_by": ["PROCESSING_EXCEPTION"],
            }, request_id, response_matched=bool(request_id), stale_response=False)
    
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
