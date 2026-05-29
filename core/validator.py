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
    
    @staticmethod
    def validate_and_adjust(action: str, confidence: float, indicators: Dict[str, Any],
                             symbol: str, bid: float, ask: float) -> Tuple[str, float]:
        """验证指标一致性并调整置信度"""
        if not indicators or action == "HOLD":
            return action, confidence
        
        rsi = indicators.get('rsi', 50)
        macd_main = indicators.get('macd_main', 0)
        macd_signal = indicators.get('macd_signal', 0)
        ema20 = indicators.get('ema20', 0)
        ema50 = indicators.get('ema50', 0)
        ema100 = indicators.get('ema100', 0)
        stoch_k = indicators.get('stoch_k', 50)
        stoch_d = indicators.get('stoch_d', 50)
        
        current_price = (bid + ask) / 2
        
        bullish_signals = 0
        bearish_signals = 0
        
        # EMA排列分析
        if current_price > ema20:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if ema20 > ema50:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if ema50 > ema100:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        # RSI分析 - 优化阈值，减少噪声
        if rsi < 35:
            bullish_signals += 1  # 超卖区域，看涨
        elif rsi > 65:
            bearish_signals += 1  # 超买区域，看跌
        # 移除中间区域的弱信号，避免过度交易
        
        # MACD分析 - 合并信号避免重复计算
        macd_histogram = macd_main - macd_signal
        # 综合MACD主线和柱状图给出加权信号
        if macd_main > 0 and macd_histogram > 0:
            bullish_signals += 1.5  # 强烈看涨：主线>0且柱状图>0
        elif macd_main < 0 and macd_histogram < 0:
            bearish_signals += 1.5  # 强烈看跌：主线<0且柱状图<0
        elif macd_histogram > 0:
            bullish_signals += 0.5  # 弱看涨：仅柱状图>0
        elif macd_histogram < 0:
            bearish_signals += 0.5  # 弱看跌：仅柱状图<0
        
        # 随机指标分析
        if stoch_k > stoch_d and stoch_k < 80:
            bullish_signals += 0.5
        elif stoch_k < stoch_d and stoch_k > 20:
            bearish_signals += 0.5
        
        if stoch_k < 20:
            bullish_signals += 0.5
        elif stoch_k > 80:
            bearish_signals += 0.5
        
        total_signals = bullish_signals + bearish_signals
        consistency = max(bullish_signals, bearish_signals) / total_signals if total_signals > 0 else 0
        
        original_action = action
        original_confidence = confidence
        
        if action == "BUY":
            if bullish_signals < config.MIN_INDICATOR_SIGNALS:
                logger.warning(f"[WARN]  BUY信号但看涨指标不足 ({bullish_signals:.1f}/6，需要至少{config.MIN_INDICATOR_SIGNALS})，降为HOLD")
                action = "HOLD"
                confidence = 0.5
            elif consistency < config.MIN_CONSISTENCY:
                logger.warning(f"[WARN]  指标一致性低 ({consistency*100:.0f}%，需要至少{config.MIN_CONSISTENCY*100:.0f}%)，降低置信度")
                confidence = confidence * 0.6
        
        elif action == "SELL":
            if bearish_signals < config.MIN_INDICATOR_SIGNALS:
                logger.warning(f"[WARN]  SELL信号但看跌指标不足 ({bearish_signals:.1f}/6，需要至少{config.MIN_INDICATOR_SIGNALS})，降为HOLD")
                action = "HOLD"
                confidence = 0.5
            elif consistency < config.MIN_CONSISTENCY:
                logger.warning(f"[WARN]  指标一致性低 ({consistency*100:.0f}%，需要至少{config.MIN_CONSISTENCY*100:.0f}%)，降低置信度")
                confidence = confidence * 0.6
        
        if original_action != action:
            logger.info(f"[REFRESH] 指标验证: 原建议={original_action} -> 调整后={action}")
        
        return action, confidence


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
