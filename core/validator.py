#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证与指标分析模块 - 优化版
提供数据验证和技术指标分析功能
"""

from typing import Dict, Any, List, Tuple, Optional
from .logger import logger
from . import config


class DataValidator:
    """数据验证器"""
    
    @staticmethod
    def validate_request(data: Dict[str, Any]) -> bool:
        """验证请求数据的完整性和有效性"""
        required_fields = ["symbol", "bid", "ask", "time"]
        
        for field in required_fields:
            if field not in data:
                raise ValueError(f"缺少必需字段: {field}")
        
        symbol = data["symbol"]
        bid = data["bid"]
        ask = data["ask"]
        current_time = data["time"]
        
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol必须是非空字符串")
        
        if not isinstance(bid, (int, float)) or bid <= 0:
            raise ValueError("bid必须是正数")
        
        if not isinstance(ask, (int, float)) or ask <= 0:
            raise ValueError("ask必须是正数")
        
        if ask <= bid:
            raise ValueError("ask必须大于bid")
        
        if not isinstance(current_time, (int, float)) or current_time <= 0:
            raise ValueError("time必须是正数时间戳")
        
        # 验证可选字段
        history = data.get("history")
        if history is not None and not isinstance(history, list):
            raise ValueError("history必须是列表")
        
        indicators = data.get("indicators")
        if indicators is not None and not isinstance(indicators, dict):
            raise ValueError("indicators必须是字典")
        
        return True


class IndicatorAnalyzer:
    """技术指标分析器 - 优化版"""

    GOLD_PIP_SIZE = 0.10
    GOLD_POINT_SIZE = 0.01

    @staticmethod
    def is_gold_symbol(symbol: str) -> bool:
        sym = (symbol or "").upper()
        return sym.startswith("XAU") or "GOLD" in sym

    @classmethod
    def price_units(cls, symbol: str) -> Dict[str, float]:
        """Return price point/pip sizes for strategy-level spread checks."""
        sym = (symbol or "").upper()
        if cls.is_gold_symbol(symbol):
            return {"point": cls.GOLD_POINT_SIZE, "pip": cls.GOLD_PIP_SIZE}
        if "JPY" in sym:
            return {"point": 0.001, "pip": 0.01}
        return {"point": 0.00001, "pip": 0.0001}

    @classmethod
    def spread_metrics(cls, symbol: str, bid: float, ask: float) -> Dict[str, float]:
        units = cls.price_units(symbol)
        spread = max(0.0, float(ask) - float(bid))
        return {
            "spread": spread,
            "spread_points": spread / units["point"] if units["point"] > 0 else 0.0,
            "spread_pips": spread / units["pip"] if units["pip"] > 0 else 0.0,
            "point_size": units["point"],
            "pip_size": units["pip"],
        }

    @staticmethod
    def _read_float(indicators: Dict[str, Any], key: str) -> Optional[float]:
        if not indicators or key not in indicators:
            return None
        try:
            return float(indicators[key])
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _label_rsi(rsi: Optional[float]) -> str:
        if rsi is None:
            return "RSI缺失"
        if rsi >= 80:
            return f"RSI={rsi:.1f}极端超买"
        if rsi > 65:
            return f"RSI={rsi:.1f}偏空/超买"
        if rsi <= 20:
            return f"RSI={rsi:.1f}极端超卖"
        if rsi < 35:
            return f"RSI={rsi:.1f}偏多/超卖反弹"
        return f"RSI={rsi:.1f}中性"
    
    @staticmethod
    def validate_and_adjust(action: str, confidence: float, indicators: Dict[str, Any],
                             symbol: str, bid: float, ask: float) -> Tuple[str, float]:
        """验证指标一致性并调整置信度，保留旧调用契约。"""
        result = IndicatorAnalyzer.evaluate_signal(action, confidence, indicators, symbol, bid, ask)
        return result["action"], result["confidence"]

    @staticmethod
    def evaluate_signal(action: str, confidence: float, indicators: Dict[str, Any],
                        symbol: str, bid: float, ask: float) -> Dict[str, Any]:
        """Return a structured local signal-quality decision."""
        original_action = (action or "HOLD").upper()
        if original_action not in {"BUY", "SELL", "HOLD"}:
            original_action = "HOLD"

        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5

        metrics = IndicatorAnalyzer.spread_metrics(symbol, bid, ask)
        current_price = (float(bid) + float(ask)) / 2
        rsi = IndicatorAnalyzer._read_float(indicators, "rsi")
        macd_main = IndicatorAnalyzer._read_float(indicators, "macd_main")
        macd_signal = IndicatorAnalyzer._read_float(indicators, "macd_signal")
        ema50 = IndicatorAnalyzer._read_float(indicators, "ema50")

        available = [
            key for key, value in (
                ("rsi", rsi),
                ("macd", None if macd_main is None or macd_signal is None else macd_main - macd_signal),
                ("ema50", ema50),
                ("spread", metrics["spread_pips"]),
            )
            if value is not None
        ]

        bullish_signals = 0.0
        bearish_signals = 0.0
        evidence: List[str] = []
        blocks: List[str] = []

        if rsi is not None:
            evidence.append(IndicatorAnalyzer._label_rsi(rsi))
            if rsi >= 80 or rsi <= 20:
                blocks.append(f"RSI极端值({rsi:.1f})")
            elif rsi < 35:
                bullish_signals += 1.0
            elif rsi > 65:
                bearish_signals += 1.0

        if macd_main is not None and macd_signal is not None:
            macd_histogram = macd_main - macd_signal
            if macd_main > 0 and macd_histogram > 0:
                bullish_signals += 1.0
                evidence.append(f"MACD偏多(hist={macd_histogram:.4f})")
            elif macd_main < 0 and macd_histogram < 0:
                bearish_signals += 1.0
                evidence.append(f"MACD偏空(hist={macd_histogram:.4f})")
            elif macd_histogram > 0:
                bullish_signals += 0.5
                evidence.append(f"MACD弱偏多(hist={macd_histogram:.4f})")
            elif macd_histogram < 0:
                bearish_signals += 0.5
                evidence.append(f"MACD弱偏空(hist={macd_histogram:.4f})")
            else:
                evidence.append("MACD中性")
        else:
            evidence.append("MACD缺失")

        if ema50 is not None and ema50 > 0:
            if current_price > ema50:
                bullish_signals += 1.0
                evidence.append(f"价格高于EMA50({current_price:.2f}>{ema50:.2f})")
            elif current_price < ema50:
                bearish_signals += 1.0
                evidence.append(f"价格低于EMA50({current_price:.2f}<{ema50:.2f})")
            else:
                evidence.append("价格贴近EMA50")
        else:
            evidence.append("EMA50缺失")

        max_spread_pips = float(getattr(config, "MAX_TRADE_SPREAD_PIPS", 3.0))
        if metrics["spread_pips"] > max_spread_pips:
            blocks.append(f"点差{metrics['spread_pips']:.1f}pips>{max_spread_pips:.1f}pips")
        else:
            evidence.append(f"点差{metrics['spread_pips']:.1f}pips可接受")

        total_directional = bullish_signals + bearish_signals
        consistency = (
            max(bullish_signals, bearish_signals) / total_directional
            if total_directional > 0 else 0.0
        )

        adjusted_action = original_action
        adjusted_confidence = confidence
        adjusted = False
        reason = "; ".join(evidence[:4])

        def downgrade(message: str, fallback_confidence: float) -> None:
            nonlocal adjusted_action, adjusted_confidence, adjusted, reason
            adjusted_action = "HOLD"
            adjusted_confidence = max(0.45, min(0.63, fallback_confidence))
            adjusted = adjusted_action != original_action or adjusted_confidence != confidence
            reason = message

        if original_action in {"BUY", "SELL"} and not indicators:
            downgrade("缺少技术指标，本地闸门降级HOLD", 0.45)
        elif original_action in {"BUY", "SELL"} and blocks:
            downgrade("; ".join(blocks), 0.55)
        elif original_action == "BUY":
            if bullish_signals < config.MIN_INDICATOR_SIGNALS:
                ratio = bullish_signals / max(config.MIN_INDICATOR_SIGNALS, 1)
                downgrade(
                    f"BUY看涨指标不足({bullish_signals:.1f}/{config.MIN_INDICATOR_SIGNALS})",
                    0.65 * ratio,
                )
            elif consistency < config.MIN_CONSISTENCY:
                reduced_confidence = confidence * 0.6
                reason_text = f"指标一致性低({consistency*100:.0f}%<{config.MIN_CONSISTENCY*100:.0f}%)"
                if reduced_confidence < config.MIN_CONFIDENCE:
                    downgrade(reason_text, reduced_confidence)
                else:
                    adjusted_confidence = reduced_confidence
                    adjusted = True
                    reason = reason_text
        elif original_action == "SELL":
            if bearish_signals < config.MIN_INDICATOR_SIGNALS:
                ratio = bearish_signals / max(config.MIN_INDICATOR_SIGNALS, 1)
                downgrade(
                    f"SELL看跌指标不足({bearish_signals:.1f}/{config.MIN_INDICATOR_SIGNALS})",
                    0.65 * ratio,
                )
            elif consistency < config.MIN_CONSISTENCY:
                reduced_confidence = confidence * 0.6
                reason_text = f"指标一致性低({consistency*100:.0f}%<{config.MIN_CONSISTENCY*100:.0f}%)"
                if reduced_confidence < config.MIN_CONFIDENCE:
                    downgrade(reason_text, reduced_confidence)
                else:
                    adjusted_confidence = reduced_confidence
                    adjusted = True
                    reason = reason_text
        elif blocks:
            reason = f"HOLD确认: {'; '.join(blocks)}"

        if adjusted_action != original_action:
            logger.info(f"[REFRESH] 指标验证: 原建议={original_action} -> 调整后={adjusted_action} ({reason})")
        elif adjusted:
            logger.info(f"[REFRESH] 指标验证: {original_action} 置信度 {confidence:.2f} -> {adjusted_confidence:.2f} ({reason})")

        return {
            "action": adjusted_action,
            "confidence": max(0.0, min(1.0, adjusted_confidence)),
            "original_action": original_action,
            "original_confidence": confidence,
            "adjusted": adjusted,
            "reason": reason,
            "bullish_signals": bullish_signals,
            "bearish_signals": bearish_signals,
            "consistency": consistency,
            "spread_pips": metrics["spread_pips"],
            "spread_points": metrics["spread_points"],
            "available_indicators": available,
            "blocks": blocks,
        }


def get_cache_key(symbol: str, bid: float, ask: float) -> str:
    """生成缓存键（精确匹配）"""
    if symbol in ['XAUUSD', 'GOLD']:
        precision = 2
    elif 'JPY' in symbol:
        precision = 3
    else:
        precision = 4
    
    return f"{symbol}_{bid:.{precision}f}_{ask:.{precision}f}"


def get_fuzzy_cache_key(symbol: str, bid: float, ask: float, tolerance_pips: float = 0.5) -> str:
    """
    生成模糊缓存键，支持价格区间匹配
    
    参数:
        symbol: 交易品种
        bid: 买入价
        ask: 卖出价
        tolerance_pips: 容忍点差（以点为单位，默认0.5点）
    
    返回:
        模糊缓存键，格式: symbol_bid_group_ask_group
    """
    # 确定品种的精度和点值
    if symbol in ['XAUUSD', 'GOLD']:
        pip_multiplier = 100  # 黄金：0.01 = 1点
        group_precision = 2
    elif 'JPY' in symbol:
        pip_multiplier = 1000  # JPY对：0.001 = 1点
        group_precision = 3
    else:
        pip_multiplier = 10000  # 大多数货币对：0.0001 = 1点
        group_precision = 4
    
    # 将价格分组到容忍区间
    bid_group = round(bid * pip_multiplier / tolerance_pips) * tolerance_pips / pip_multiplier
    ask_group = round(ask * pip_multiplier / tolerance_pips) * tolerance_pips / pip_multiplier
    
    return f"{symbol}_g{bid_group:.{group_precision}f}_g{ask_group:.{group_precision}f}"


def get_cache_keys_for_lookup(symbol: str, bid: float, ask: float) -> List[str]:
    """
    生成用于缓存查找的多个键（精确键 + 多个模糊键）
    
    返回:
        缓存键列表，按精确度排序（最精确的在前）
    """
    keys = []
    
    # 1. 精确键（最高优先级）
    keys.append(get_cache_key(symbol, bid, ask))
    
    # 2. 不同容忍度的模糊键
    tolerance_levels = [0.1, 0.5, 1.0, 2.0]  # 以点为单位的容忍度
    
    for tolerance in tolerance_levels:
        fuzzy_key = get_fuzzy_cache_key(symbol, bid, ask, tolerance)
        if fuzzy_key not in keys:
            keys.append(fuzzy_key)
    
    return keys
