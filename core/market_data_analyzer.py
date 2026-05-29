#!/usr/bin/env python3
"""
科学智能交易系统 - 多维度市场数据分析模块
集成实时行情、历史数据、宏观经济指标和市场情绪分析
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import threading
import queue

import requests
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

from core.logger import logger
from core.datastore import get_datastore
from core.config import Config


class DataSource(Enum):
    """数据来源"""
    MT5 = "mt5"
    ALPACA = "alpaca"
    YAHOO_FINANCE = "yahoo"
    FRED = "fred"  # 美联储经济数据
    OANDA = "oanda"
    TRADINGVIEW = "tradingview"
    CRYPTO_COMPARE = "crypto_compare"


class TimeFrame(Enum):
    """时间框架"""
    TICK = "tick"
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


@dataclass
class MarketPrice:
    """市场行情数据结构"""
    symbol: str
    timeframe: str
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    tick_volume: Optional[float] = None
    spread: Optional[int] = None
    real_volume: Optional[float] = None
    source: str = DataSource.MT5.value


@dataclass
class TechnicalIndicators:
    """技术指标数据结构"""
    symbol: str
    timeframe: str
    timestamp: float
    # 移动平均线
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma50: Optional[float] = None
    ma100: Optional[float] = None
    ma200: Optional[float] = None
    # 振荡器
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_hist: Optional[float] = None
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None
    cci: Optional[float] = None
    # 趋势指标
    adx: Optional[float] = None
    # 波动率指标
    atr: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    # 成交量指标
    obv: Optional[float] = None
    volume_ratio: Optional[float] = None


class MarketDataAnalyzer:
    """多维度市场数据分析器"""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.datastore = get_datastore()
        
        # 数据缓存
        self.price_cache: Dict[str, List[MarketPrice]] = {}
        self.indicator_cache: Dict[str, List[TechnicalIndicators]] = {}
        
        # 数据队列
        self.data_queue = queue.Queue()
        
        # 运行状态
        self.running = False
        self.analysis_thread: Optional[threading.Thread] = None
        
        # 外部数据API配置
        self.alpha_vantage_key = self.config.get("ALPHA_VANTAGE_KEY", "")
        self.fred_api_key = self.config.get("FRED_API_KEY", "")
        
        logger.info("[DATA] 多维度市场数据分析器初始化完成")
    
    def start(self):
        """启动数据分析器"""
        if self.running:
            logger.warning("[WARN]  数据分析器已在运行中")
            return
        
        self.running = True
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        logger.info("-> 市场数据分析器已启动")
    
    def stop(self):
        """停止数据分析器"""
        self.running = False
        if self.analysis_thread:
            self.analysis_thread.join(timeout=5)
        logger.info("🛑 市场数据分析器已停止")
    
    def _analysis_loop(self):
        """数据分析主循环"""
        logger.info("[REFRESH] 数据分析循环开始")
        
        while self.running:
            try:
                # 处理数据队列中的新数据
                self._process_queued_data()
                
                # 定期更新技术指标
                self._update_technical_indicators()
                
                # 定期获取宏观经济数据
                self._update_economic_data()
                
                # 定期获取市场情绪数据
                self._update_market_sentiment()
                
                time.sleep(1)  # 每秒检查一次
                
            except Exception as e:
                logger.error(f"[ERR] 数据分析循环异常: {e}")
                time.sleep(5)
    
    def _process_queued_data(self):
        """处理队列中的市场数据"""
        processed = 0
        while not self.data_queue.empty() and processed < 100:
            try:
                data = self.data_queue.get_nowait()
                self._process_market_data(data)
                self.data_queue.task_done()
                processed += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"[ERR] 处理市场数据失败: {e}")
    
    def add_market_data(self, data: Dict[str, Any]):
        """添加市场数据到处理队列"""
        self.data_queue.put(data)
    
    def _process_market_data(self, data: Dict[str, Any]):
        """处理单个市场数据点"""
        try:
            symbol = data.get("symbol", "")
            if not symbol:
                logger.warning("[WARN]  市场数据缺少symbol字段")
                return
            
            # 检查数据类型
            data_type = data.get("type", "")
            
            if data_type == "price":
                self._process_price_data(data)
            elif data_type == "indicator":
                self._process_indicator_data(data)
            elif data_type == "economic":
                self._process_economic_data(data)
            elif data_type == "sentiment":
                self._process_sentiment_data(data)
            else:
                logger.warning(f"[WARN]  未知数据类型: {data_type}")
                
        except Exception as e:
            logger.error(f"[ERR] 处理市场数据失败: {e}")
    
    def _process_price_data(self, data: Dict[str, Any]):
        """处理价格数据"""
        try:
            symbol = data["symbol"]
            timeframe = data.get("timeframe", "M1")
            timestamp = data.get("timestamp", time.time())
            
            price = MarketPrice(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=data.get("open", 0),
                high=data.get("high", 0),
                low=data.get("low", 0),
                close=data.get("close", 0),
                volume=data.get("volume"),
                tick_volume=data.get("tick_volume"),
                spread=data.get("spread"),
                real_volume=data.get("real_volume"),
                source=data.get("source", DataSource.MT5.value)
            )
            
            # 存储到数据库
            price_id = self.datastore.record_market_price(
                symbol=price.symbol,
                timeframe=price.timeframe,
                open_price=price.open,
                high=price.high,
                low=price.low,
                close=price.close,
                volume=price.volume,
                tick_volume=price.tick_volume,
                spread=price.spread,
                real_volume=price.real_volume
            )
            
            # 更新缓存
            cache_key = f"{symbol}_{timeframe}"
            if cache_key not in self.price_cache:
                self.price_cache[cache_key] = []
            
            self.price_cache[cache_key].append(price)
            if len(self.price_cache[cache_key]) > 1000:
                self.price_cache[cache_key] = self.price_cache[cache_key][-500:]
            
            logger.debug(f"[DATA] 价格数据处理完成 [ID: {price_id}]: {symbol} {timeframe} {price.close}")
            
        except KeyError as e:
            logger.error(f"[ERR] 价格数据缺少必要字段: {e}")
        except Exception as e:
            logger.error(f"[ERR] 处理价格数据失败: {e}")
    
    def _process_indicator_data(self, data: Dict[str, Any]):
        """处理技术指标数据"""
        try:
            symbol = data["symbol"]
            timeframe = data.get("timeframe", "M1")
            
            indicators = TechnicalIndicators(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=data.get("timestamp", time.time()),
                ma5=data.get("ma5"),
                ma10=data.get("ma10"),
                ma20=data.get("ma20"),
                ma50=data.get("ma50"),
                ma100=data.get("ma100"),
                ma200=data.get("ma200"),
                rsi=data.get("rsi"),
                macd=data.get("macd"),
                macd_signal=data.get("macd_signal"),
                macd_hist=data.get("macd_hist"),
                bollinger_upper=data.get("bollinger_upper"),
                bollinger_middle=data.get("bollinger_middle"),
                bollinger_lower=data.get("bollinger_lower"),
                atr=data.get("atr"),
                stoch_k=data.get("stoch_k"),
                stoch_d=data.get("stoch_d"),
                cci=data.get("cci"),
                adx=data.get("adx"),
                obv=data.get("obv"),
                volume_ratio=data.get("volume_ratio")
            )
            
            # 存储到数据库
            indicator_id = self.datastore.record_technical_indicators(
                symbol=indicators.symbol,
                timeframe=indicators.timeframe,
                ma5=indicators.ma5,
                ma10=indicators.ma10,
                ma20=indicators.ma20,
                ma50=indicators.ma50,
                ma100=indicators.ma100,
                ma200=indicators.ma200,
                rsi=indicators.rsi,
                macd=indicators.macd,
                macd_signal=indicators.macd_signal,
                macd_hist=indicators.macd_hist,
                bollinger_upper=indicators.bollinger_upper,
                bollinger_middle=indicators.bollinger_middle,
                bollinger_lower=indicators.bollinger_lower,
                atr=indicators.atr,
                stoch_k=indicators.stoch_k,
                stoch_d=indicators.stoch_d,
                cci=indicators.cci,
                adx=indicators.adx,
                obv=indicators.obv,
                volume_ratio=indicators.volume_ratio
            )
            
            # 更新缓存
            cache_key = f"{symbol}_{timeframe}_indicators"
            if cache_key not in self.indicator_cache:
                self.indicator_cache[cache_key] = []
            
            self.indicator_cache[cache_key].append(indicators)
            if len(self.indicator_cache[cache_key]) > 500:
                self.indicator_cache[cache_key] = self.indicator_cache[cache_key][-250:]
            
            logger.debug(f"[UP] 技术指标处理完成 [ID: {indicator_id}]: {symbol} {timeframe}")
            
        except KeyError as e:
            logger.error(f"[ERR] 技术指标数据缺少必要字段: {e}")
        except Exception as e:
            logger.error(f"[ERR] 处理技术指标数据失败: {e}")
    
    def _process_economic_data(self, data: Dict[str, Any]):
        """处理宏观经济数据"""
        try:
            country = data.get("country", "USA")
            indicator_name = data.get("indicator_name", "")
            indicator_code = data.get("indicator_code", "")
            
            if not indicator_name or not indicator_code:
                logger.warning("[WARN]  宏观经济数据缺少必要字段")
                return
            
            econ_id = self.datastore.record_economic_indicator(
                country=country,
                indicator_name=indicator_name,
                indicator_code=indicator_code,
                value=data.get("value", 0),
                unit=data.get("unit", ""),
                period=data.get("period", ""),
                previous_value=data.get("previous_value"),
                forecast_value=data.get("forecast_value"),
                source=data.get("source", "unknown")
            )
            
            logger.debug(f"🌍 宏观经济数据处理完成 [ID: {econ_id}]: {country} {indicator_code}")
            
        except Exception as e:
            logger.error(f"[ERR] 处理宏观经济数据失败: {e}")
    
    def _process_sentiment_data(self, data: Dict[str, Any]):
        """处理市场情绪数据"""
        try:
            symbol = data.get("symbol", "")
            if not symbol:
                logger.warning("[WARN]  市场情绪数据缺少symbol字段")
                return
            
            sentiment_id = self.datastore.record_market_sentiment(
                symbol=symbol,
                sentiment_score=data.get("sentiment_score"),
                bullish_percent=data.get("bullish_percent"),
                bearish_percent=data.get("bearish_percent"),
                neutral_percent=data.get("neutral_percent"),
                news_sentiment=data.get("news_sentiment"),
                social_sentiment=data.get("social_sentiment"),
                fear_greed_index=data.get("fear_greed_index"),
                volatility_index=data.get("volatility_index"),
                put_call_ratio=data.get("put_call_ratio"),
                source=data.get("source", "unknown")
            )
            
            logger.debug(f"😊 市场情绪数据处理完成 [ID: {sentiment_id}]: {symbol}")
            
        except Exception as e:
            logger.error(f"[ERR] 处理市场情绪数据失败: {e}")
    
    def _update_technical_indicators(self):
        """更新技术指标（基于最新价格数据）"""
        try:
            # 获取主要交易品种
            symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "XAUUSD"]
            
            for symbol in symbols:
                cache_key = f"{symbol}_M1"
                if cache_key in self.price_cache and len(self.price_cache[cache_key]) >= 20:
                    # 计算技术指标
                    prices = self.price_cache[cache_key][-100:]  # 使用最近100个价格
                    if len(prices) >= 20:
                        indicators = self._calculate_technical_indicators(prices, symbol, "M1")
                        if indicators:
                            # 添加到处理队列
                            indicator_data = {
                                "type": "indicator",
                                "symbol": symbol,
                                "timeframe": "M1",
                                "timestamp": time.time(),
                                **indicators
                            }
                            self.add_market_data(indicator_data)
                            
        except Exception as e:
            logger.error(f"[ERR] 更新技术指标失败: {e}")
    
    def _calculate_technical_indicators(self, prices: List[MarketPrice], symbol: str, timeframe: str) -> Optional[Dict[str, float]]:
        """计算技术指标"""
        try:
            if len(prices) < 20:
                return None
            
            # 提取收盘价序列
            close_prices = [p.close for p in prices]
            high_prices = [p.high for p in prices]
            low_prices = [p.low for p in prices]
            volumes = [p.volume or 0 for p in prices]
            
            # 转换为numpy数组
            close_np = np.array(close_prices)
            high_np = np.array(high_prices)
            low_np = np.array(low_prices)
            volume_np = np.array(volumes)
            
            indicators = {}
            
            # 计算移动平均线
            if len(close_np) >= 5:
                indicators["ma5"] = float(np.mean(close_np[-5:]))
            if len(close_np) >= 10:
                indicators["ma10"] = float(np.mean(close_np[-10:]))
            if len(close_np) >= 20:
                indicators["ma20"] = float(np.mean(close_np[-20:]))
            if len(close_np) >= 50:
                indicators["ma50"] = float(np.mean(close_np[-50:]))
            if len(close_np) >= 100:
                indicators["ma100"] = float(np.mean(close_np[-100:]))
            if len(close_np) >= 200:
                indicators["ma200"] = float(np.mean(close_np[-200:]))
            
            # 计算RSI（简化版）
            if len(close_np) >= 14:
                deltas = np.diff(close_np)
                gains = deltas[deltas > 0]
                losses = -deltas[deltas < 0]
                
                if len(gains) > 0 and len(losses) > 0:
                    avg_gain = np.mean(gains[-14:])
                    avg_loss = np.mean(losses[-14:])
                    
                    if avg_loss != 0:
                        rs = avg_gain / avg_loss
                        rsi = 100 - (100 / (1 + rs))
                        indicators["rsi"] = float(rsi)
            
            # 计算布林带（简化版）
            if len(close_np) >= 20:
                ma20 = indicators.get("ma20", np.mean(close_np[-20:]))
                std = np.std(close_np[-20:])
                indicators["bollinger_middle"] = float(ma20)
                indicators["bollinger_upper"] = float(ma20 + 2 * std)
                indicators["bollinger_lower"] = float(ma20 - 2 * std)
            
            # 计算ATR（简化版）
            if len(high_np) >= 14 and len(low_np) >= 14:
                tr = np.maximum(
                    high_np[-1] - low_np[-1],
                    np.abs(high_np[-1] - close_np[-2]),
                    np.abs(low_np[-1] - close_np[-2])
                )
                indicators["atr"] = float(tr)
            
            # 计算成交量比率
            if len(volume_np) >= 20:
                avg_volume = np.mean(volume_np[-20:])
                if avg_volume > 0:
                    indicators["volume_ratio"] = float(volume_np[-1] / avg_volume)
            
            return indicators
            
        except Exception as e:
            logger.error(f"[ERR] 计算技术指标失败: {e}")
            return None
    
    def _update_economic_data(self):
        """更新宏观经济数据（示例）"""
        try:
            # 这里可以集成FRED API或其他经济数据API
            # 目前仅作为示例，实际使用时需要配置API密钥
            
            if not self.fred_api_key:
                return
            
            # 示例：获取美国CPI数据
            # 实际实现需要调用FRED API
            cpi_data = {
                "type": "economic",
                "country": "USA",
                "indicator_name": "Consumer Price Index",
                "indicator_code": "CPIAUCSL",
                "value": 310.0,  # 示例值
                "unit": "Index",
                "period": "monthly",
                "previous_value": 309.5,
                "forecast_value": 310.2,
                "source": "FRED"
            }
            
            self.add_market_data(cpi_data)
            
        except Exception as e:
            logger.error(f"[ERR] 更新宏观经济数据失败: {e}")
    
    def _update_market_sentiment(self):
        """更新市场情绪数据（示例）"""
        try:
            symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD"]
            
            for symbol in symbols:
                # 示例情绪数据，实际应集成外部API
                sentiment_data = {
                    "type": "sentiment",
                    "symbol": symbol,
                    "sentiment_score": np.random.uniform(-1, 1),
                    "bullish_percent": np.random.uniform(30, 70),
                    "bearish_percent": np.random.uniform(20, 60),
                    "neutral_percent": np.random.uniform(10, 40),
                    "news_sentiment": np.random.uniform(-0.5, 0.5),
                    "social_sentiment": np.random.uniform(-0.5, 0.5),
                    "fear_greed_index": np.random.uniform(20, 80),
                    "volatility_index": np.random.uniform(10, 30),
                    "put_call_ratio": np.random.uniform(0.5, 1.5),
                    "source": "simulated"
                }
                
                self.add_market_data(sentiment_data)
                
        except Exception as e:
            logger.error(f"[ERR] 更新市场情绪数据失败: {e}")
    
    def get_market_analysis(self, symbol: str, timeframe: str = "M1") -> Dict[str, Any]:
        """获取市场综合分析"""
        try:
            cache_key = f"{symbol}_{timeframe}"
            
            # 获取价格数据
            prices = self.price_cache.get(cache_key, [])
            indicators = self.indicator_cache.get(f"{cache_key}_indicators", [])
            
            analysis = {
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": time.time(),
                "current_price": prices[-1].close if prices else 0,
                "price_trend": self._calculate_price_trend(prices),
                "volatility": self._calculate_volatility(prices),
                "volume_analysis": self._analyze_volume(prices),
                "technical_score": self._calculate_technical_score(indicators),
                "market_sentiment": self._get_current_sentiment(symbol),
                "recommendation": self._generate_recommendation(prices, indicators)
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"[ERR] 获取市场分析失败: {e}")
            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "error": str(e)
            }
    
    def _calculate_price_trend(self, prices: List[MarketPrice]) -> str:
        """计算价格趋势"""
        if len(prices) < 10:
            return "neutral"
        
        recent_prices = [p.close for p in prices[-10:]]
        if len(recent_prices) < 2:
            return "neutral"
        
        # 简单趋势判断
        price_change = recent_prices[-1] - recent_prices[0]
        if price_change > 0:
            return "bullish"
        elif price_change < 0:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_volatility(self, prices: List[MarketPrice]) -> float:
        """计算波动率"""
        if len(prices) < 20:
            return 0.0
        
        close_prices = [p.close for p in prices[-20:]]
        returns = np.diff(close_prices) / close_prices[:-1]
        volatility = np.std(returns) * np.sqrt(252)  # 年化波动率（简化）
        
        return float(volatility)
    
    def _analyze_volume(self, prices: List[MarketPrice]) -> Dict[str, Any]:
        """分析成交量"""
        if len(prices) < 20:
            return {"trend": "neutral", "ratio": 1.0}
        
        volumes = [p.volume or 0 for p in prices[-20:]]
        avg_volume = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
        current_volume = volumes[-1] if volumes else 0
        
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        if volume_ratio > 1.5:
            trend = "high"
        elif volume_ratio > 0.8:
            trend = "normal"
        else:
            trend = "low"
        
        return {
            "trend": trend,
            "ratio": float(volume_ratio),
            "current_volume": current_volume,
            "average_volume": float(avg_volume)
        }
    
    def _calculate_technical_score(self, indicators: List[TechnicalIndicators]) -> float:
        """计算技术分析综合得分"""
        if not indicators:
            return 0.5
        
        latest = indicators[-1] if indicators else None
        if not latest:
            return 0.5
        
        score = 0.5  # 中性基准
        
        # RSI得分
        if latest.rsi:
            if latest.rsi < 30:
                score += 0.2  # 超卖，看涨
            elif latest.rsi > 70:
                score -= 0.2  # 超买，看跌
        
        # 移动平均线得分
        if latest.ma5 and latest.ma20:
            if latest.ma5 > latest.ma20:
                score += 0.1  # 短期均线上穿长期，看涨
            else:
                score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _get_current_sentiment(self, symbol: str) -> Dict[str, Any]:
        """获取当前市场情绪"""
        # 简化实现，实际应从数据库或API获取
        return {
            "score": 0.5,
            "trend": "neutral",
            "bullish": 50,
            "bearish": 30,
            "neutral": 20
        }
    
    def _generate_recommendation(self, prices: List[MarketPrice], indicators: List[TechnicalIndicators]) -> Dict[str, Any]:
        """生成交易建议"""
        technical_score = self._calculate_technical_score(indicators)
        
        if technical_score > 0.7:
            action = "BUY"
            confidence = technical_score
            reason = "技术指标强烈看涨"
        elif technical_score < 0.3:
            action = "SELL"
            confidence = 1.0 - technical_score
            reason = "技术指标强烈看跌"
        else:
            action = "HOLD"
            confidence = 0.5
            reason = "技术指标中性，建议观望"
        
        return {
            "action": action,
            "confidence": float(confidence),
            "reason": reason,
            "timestamp": time.time()
        }


# 全局数据分析器实例
_global_analyzer: Optional[MarketDataAnalyzer] = None


def get_market_data_analyzer() -> MarketDataAnalyzer:
    """获取全局市场数据分析器实例"""
    global _global_analyzer
    if not _global_analyzer:
        _global_analyzer = MarketDataAnalyzer()
    return _global_analyzer


if __name__ == "__main__":
    # 测试市场数据分析器
    print("="*70)
    print("[TOOL] 测试市场数据分析系统")
    print("="*70)
    
    analyzer = MarketDataAnalyzer()
    
    # 添加示例价格数据
    print("\n[DATA] 添加示例价格数据...")
    for i in range(100):
        price_data = {
            "type": "price",
            "symbol": "EURUSD",
            "timeframe": "M1",
            "timestamp": time.time() - (100 - i) * 60,
            "open": 1.0850 + np.random.uniform(-0.001, 0.001),
            "high": 1.0860 + np.random.uniform(-0.001, 0.001),
            "low": 1.0840 + np.random.uniform(-0.001, 0.001),
            "close": 1.0855 + np.random.uniform(-0.001, 0.001),
            "volume": np.random.uniform(1000, 10000),
            "source": "simulated"
        }
        analyzer.add_market_data(price_data)
    
    # 启动分析器
    analyzer.start()
    
    # 等待处理
    time.sleep(2)
    
    # 获取市场分析
    print("\n[UP] 获取市场分析...")
    analysis = analyzer.get_market_analysis("EURUSD", "M1")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))
    
    # 停止分析器
    analyzer.stop()
    
    print("\n[OK] 市场数据分析器测试完成！")