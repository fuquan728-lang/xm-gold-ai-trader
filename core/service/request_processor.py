# -*- coding: utf-8 -*-
"""
RequestProcessor - 请求处理管道 (Phase 3)
负责请求验证、数据准备、AI分析委托、响应构建

从 MT5AITradingService.process_request() 拆分而来 (2026-07-04)
"""

import time
import traceback
from datetime import datetime
from typing import Dict, Any, Optional

from core.logger import logger, monitor
from core.mql5_data import get_mql5_data_manager
from core import config
from core.service.utils import (
    utc_now_iso,
    latency_ms,
    total_latency_ms,
    derive_blocked_by,
)

PROTOCOL_VERSION = "v0.25.7"


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


class RequestProcessor:
    """请求处理管道
    封装：验证 → 数据准备 → AI分析 → 后处理 → 响应构建
    """

    def __init__(
        self,
        ai_coordinator,
        validator,
        local_instance=None,
        trading_recorder=None,
        web_dashboard=None,
        monitor_module=None,
    ):
        self._ai_coordinator = ai_coordinator
        self._validator = validator
        self._local_instance = local_instance
        self._trading_recorder = trading_recorder
        self._web_dashboard = web_dashboard
        self._monitor = monitor_module

    def process(self, request_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """处理完整的请求管道"""
        try:
            # 高可用架构统计
            if self._local_instance:
                self._local_instance.increment_requests()

            if not isinstance(request_data, dict):
                raise ValueError("请求数据必须是JSON对象")

            # MQL5 数据捷径
            if request_data.get("type") == "mql5_data":
                mql5_manager = get_mql5_data_manager()
                success = mql5_manager.update_from_json(request_data)
                return _build_protocol_response(
                    {
                        "status": "ok" if success else "error",
                        "action": "HOLD",
                        "confidence": 0.0,
                        "reason": "MQL5数据更新" if success else "MQL5数据更新失败",
                        "use_deepseek": False,
                        "cached": False,
                    },
                    str(request_data.get("request_id", "")),
                    response_matched=bool(request_data.get("request_id")),
                )

            request_id = str(request_data.get("request_id", "")).strip()
            request_created_at = request_data.get("request_created_at") or request_data.get("timestamp")
            request_read_at = request_data.get("_request_read_at") or utc_now_iso()
            ea_timeout_seconds = request_data.get("ea_timeout_seconds")

            if not request_id:
                return _build_protocol_response(
                    {
                        "action": "HOLD",
                        "confidence": 0.0,
                        "reason": "Missing request_id; request ignored for stale-response safety",
                        "symbol": str(request_data.get("symbol", "UNKNOWN")),
                        "analysis_time": utc_now_iso(),
                        "use_deepseek": False,
                        "cached": False,
                        "request_created_at": request_created_at,
                        "request_read_at": request_read_at,
                        "ai_started_at": None,
                        "ai_finished_at": None,
                        "latency_total_ms": total_latency_ms(request_created_at, request_read_at, utc_now_iso()),
                        "latency_ai_ms": None,
                        "response_matched": False,
                        "stale_response": False,
                        "ea_timeout_seconds": ea_timeout_seconds,
                        "blocked_by": ["MISSING_REQUEST_ID"],
                    },
                    "",
                    response_matched=False,
                    stale_response=False,
                )

            # ---- 请求验证 ----
            validated_request = dict(request_data)
            try:
                validated_request["bid"] = float(validated_request.get("bid"))
                validated_request["ask"] = float(validated_request.get("ask"))
                validated_request["time"] = float(validated_request.get("time", int(time.time())))
                self._validator.validate_request(validated_request)
            except Exception as validation_error:
                logger.warning(f"[SAFE] 请求校验失败，返回HOLD: {validation_error}")
                return _build_protocol_response(
                    {
                        "action": "HOLD",
                        "confidence": 0.0,
                        "reason": f"请求校验失败: {validation_error}",
                        "symbol": str(request_data.get("symbol", "UNKNOWN")),
                        "analysis_time": utc_now_iso(),
                        "use_deepseek": False,
                        "cached": False,
                        "request_created_at": request_created_at,
                        "request_read_at": request_read_at,
                        "ai_started_at": None,
                        "ai_finished_at": None,
                        "latency_total_ms": total_latency_ms(request_created_at, request_read_at, utc_now_iso()),
                        "latency_ai_ms": None,
                        "response_matched": True,
                        "stale_response": False,
                        "ea_timeout_seconds": ea_timeout_seconds,
                        "blocked_by": ["REQUEST_VALIDATION_FAILED"],
                    },
                    request_id,
                    response_matched=True,
                    stale_response=False,
                )

            symbol = validated_request["symbol"].strip()
            bid = validated_request["bid"]
            ask = validated_request["ask"]
            current_time = validated_request["time"]
            history = request_data.get("history")
            indicators = request_data.get("indicators")

            # 兼容EA的扁平JSON格式
            if not isinstance(indicators, dict):
                flat_indicators = {}
                for key in ("rsi", "macd_main", "macd_signal", "ema50", "atr", "stochastic_k", "stochastic_d"):
                    if key in request_data and request_data[key] is not None:
                        flat_indicators[key] = request_data[key]
                if flat_indicators:
                    indicators = flat_indicators
                    logger.debug(f"[DATA] 从EA扁平JSON提取指标: {list(flat_indicators.keys())}")

            multi_timeframe = request_data.get("multi_timeframe")
            account_data = request_data.get("account_data")
            trade_history = request_data.get("trade_history", [])

            # ---- 账户数据更新 ----
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

            # ---- 交易统计更新 ----
            if isinstance(trade_history, list) and trade_history:
                if self._monitor:
                    self._monitor.update_trade_stats(trade_history)

            # ---- AI 分析 ----
            logger.info(f"收到请求: {symbol} Bid={bid} Ask={ask}")
            ai_started_at = utc_now_iso()
            result = self._ai_coordinator.analyze(
                symbol, bid, ask, current_time, history, indicators, multi_timeframe
            )
            ai_finished_at = utc_now_iso()

            if result:
                payload = dict(result)
                payload["request_created_at"] = request_created_at
                payload["request_read_at"] = request_read_at
                payload["ai_started_at"] = ai_started_at
                payload["ai_finished_at"] = ai_finished_at
                payload["latency_ai_ms"] = latency_ms(ai_started_at, ai_finished_at)
                payload["latency_total_ms"] = total_latency_ms(request_created_at, request_read_at, ai_finished_at)
                payload["response_matched"] = True
                payload["stale_response"] = False
                payload["ea_timeout_seconds"] = ea_timeout_seconds
                payload["blocked_by"] = derive_blocked_by(payload, config)
                result = _build_protocol_response(payload, request_id, response_matched=True, stale_response=False)

            # ---- Dashboard 更新 ----
            if result and self._web_dashboard:
                self._web_dashboard.add_signal(result)
                self._web_dashboard.record_request(True)

            # ---- 交易记录 ----
            if result and self._trading_recorder:
                action = result.get("action", "HOLD")
                confidence = result.get("confidence", 0)

                self._trading_recorder.record_analysis(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    action=action,
                    confidence=confidence,
                    reason=result.get("reason", ""),
                    use_deepseek=result.get("use_deepseek", False),
                    cached=result.get("cached", False),
                    indicators=indicators,
                    history=history,
                )

                if action in ("BUY", "SELL") and confidence > 0.5:
                    entry_price = ask if action == "BUY" else bid
                    trade_data = {
                        "symbol": symbol,
                        "action": action,
                        "entry_price": entry_price,
                        "exit_price": None,
                        "pnl": None,
                        "status": "open",
                        "confidence": confidence,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if self._web_dashboard:
                        self._web_dashboard.add_trade(trade_data)
                    logger.info(f"[LOG] 记录开仓信号: {action} {symbol} @ {entry_price:.5f}")

            return result

        except Exception as e:
            logger.error(f"[ERR] 处理请求失败: {e}")
            logger.error(f"   堆栈: {traceback.format_exc()}")
            monitor.record_request(False, 0)
            if self._web_dashboard:
                self._web_dashboard.record_request(False)
            request_id = str(request_data.get("request_id", "")) if isinstance(request_data, dict) else ""
            return _build_protocol_response(
                {
                    "action": "HOLD",
                    "confidence": 0.0,
                    "reason": f"处理请求异常: {str(e)}",
                    "analysis_time": utc_now_iso(),
                    "use_deepseek": False,
                    "cached": False,
                    "response_matched": bool(isinstance(request_data, dict) and request_data.get("request_id")),
                    "stale_response": False,
                    "blocked_by": ["PROCESSING_EXCEPTION"],
                },
                request_id,
                response_matched=bool(request_id),
                stale_response=False,
            )
