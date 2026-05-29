#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI分析引擎 - 优化版
提供DeepSeek API集成和智能分析功能
"""

import json
import re
import random
import time
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from .logger import logger
from .http_client import get_http_client
from .cache import global_cache
from . import config
from .weight_optimizer import get_weight_optimizer, WeightOptimizer, TradeSignal
from .mql5_data import get_mql5_data_manager


class AIAnalyzer:
    """AI分析引擎 - 优化版（带权重优化）"""
    INVALID_API_KEYS = {
        "",
        "your-api-key-here",
        "your-deepseek-api-key-here",
    }
    
    def __init__(self):
        self.api_key = config.DEEPSEEK_API_KEY
        self.api_url = config.DEEPSEEK_API_URL
        self.model = config.DEEPSEEK_MODEL
        self.use_deepseek = config.USE_DEEPSEEK
        self.http_client = get_http_client(
            max_retries=config.MAX_RETRIES,
            pool_size=config.CONNECTION_POOL_SIZE,
            timeout=config.REQUEST_TIMEOUT
        )
        # 权重优化器
        self.weight_optimizer = get_weight_optimizer()
        # MQL5数据管理器
        self.mql5_data_manager = get_mql5_data_manager()

    def has_valid_api_key(self) -> bool:
        """检查DeepSeek API Key是否看起来可用。"""
        api_key = (self.api_key or "").strip()
        return bool(api_key) and api_key not in self.INVALID_API_KEYS and not api_key.lower().startswith("your-")

    def is_deepseek_available(self) -> bool:
        """DeepSeek是否已启用且已配置有效密钥。"""
        return self.use_deepseek and self.has_valid_api_key()

    def get_deepseek_status(self) -> str:
        """返回便于日志展示的DeepSeek配置状态。"""
        if not self.use_deepseek:
            return "禁用"
        if not self.has_valid_api_key():
            return "密钥未设置"
        return "启用"
    
    def build_prompt(self, symbol: str, bid: float, ask: float, current_time: float,
                    history: Optional[List[Dict]] = None,
                    indicators: Optional[Dict] = None,
                    multi_timeframe: Optional[Dict[str, Any]] = None,
                    include_account_context: bool = True) -> str:
        """构建优化后的提示词 - V3.2增强版（集成实时账户数据）"""
        current_price = (bid + ask) / 2
        spread = ask - bid
        now_str = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        # UTC时间辅助判断市场活跃时段
        utc_hour = datetime.utcfromtimestamp(current_time).hour
        
        # 判断市场时段
        if 7 <= utc_hour <= 16:
            session_hint = "当前处于欧洲-美洲重叠时段(高流动性)"
        elif 0 <= utc_hour <= 8:
            session_hint = "当前处于亚洲时段(中流动性)"
        else:
            session_hint = "当前处于低流动性时段，需谨慎交易"
        
        # 获取实时账户数据（如果启用）
        account_context_section = ""
        if include_account_context:
            account_context_section = self._build_account_context_section(symbol)
        
        prompt = f"""你是一位专业的高级量化交易分析师，拥有20年外汇与大宗商品交易经验。

【角色与纪律】
- 你是纪律严明的风险管理优先型交易员
- 你的首要目标是保护本金，其次才是追求盈利
- 绝不在指标信号矛盾时强行开仓
- 决策时需综合考虑实时账户状况和已有持仓

【市场基本数据】
- 交易品种: {symbol}
- 当前时间: {now_str} (UTC{utc_hour}:00)
- {session_hint}
- Bid: {bid} | Ask: {ask} | 中间价: {current_price}
- 点差: {spread:.5f} ({spread/current_price*10000:.1f}点)

【返回格式要求 - 严格遵守】
只返回纯JSON，不要任何其他文字、代码块标记或解释：
{{"action": "BUY或SELL或HOLD", "confidence": 0.0到1.0, "reason": "简要分析原因（50字内）", "stop_loss_pips": 建议止损pips数(25-150), "take_profit_pips": 建议止盈pips数(40-300)}}

【止损止盈规则 - 重要：单位为pip，1pip=0.10美元】
- 止损pips: 最小25pips($2.50)，建议黄金40-80pips($4-8)，高波动可用100pips($10)
- 止盈pips: 风险回报比至少1.5:1，建议黄金80-150pips($8-15)
- 高置信度(>0.8)可适当扩大止盈，低置信度(<0.7)建议保守，止损收窄
- 止损绝对不能大于止盈的一半（保证盈亏比）
- HOLD信号时，stop_loss_pips和take_profit_pips字段可省略

【决策规则 - 层次化评估】
第一层（一票否决）：
  - RSI > 80 或 RSI < 20 → 必须HOLD（极端超买/超卖，行情随时反转）
  - 点差异常偏大（> 正常值3倍）→ 必须HOLD（流动性不足）

第二层（多指标确认）：
  - 至少3个指标方向一致才可发出BUY/SELL信号
  - 只有1-2个指标一致 → HOLD

第三层（置信度校准 - 注意增加随机性）：
  - 5个指标全部一致 + 多周期共振强 → confidence 0.88-0.95
  - 5个指标全部一致 → confidence 0.82-0.90
  - 4个指标一致 + 趋势明确 → confidence 0.75-0.82
  - 4个指标一致 → confidence 0.70-0.78
  - 3个指标一致 + 风险可控 → confidence 0.65-0.72
  - 3个指标一致 → confidence 0.58-0.65
  - 不足3个 → 必须HOLD
  - 重要：避免频繁返回相同值(0.72/0.82)，在不同情况下返回不同置信度

第四层（账户风险考量）：
  - 当前品种已有持仓过重 → 降低仓位或放弃交易
  - 保证金水平不足 → 必须HOLD或大幅降低仓位
  - 账户已有较大回撤 → 建议保守或观望

置信度阈值: {config.MIN_CONFIDENCE}（低于此值的信号视为无效）
【重要】置信度等级说明：
  - 0.88-0.95：强共振（5指标全一致+多周期共振）
  - 0.82-0.90：强信号（5指标全一致）
  - 0.75-0.82：中等偏强（4指标一致+明确趋势）
  - 0.70-0.78：中等信号（4指标一致）
  - 0.65-0.72：偏弱信号（3指标一致+风险可控）
  - 0.58-0.65：边缘信号（3指标一致，谨慎）
  - <0.58：信号不足 → 必须HOLD
"""
        
        # 添加账户上下文部分
        if account_context_section:
            prompt += account_context_section
        
        if indicators:
            prompt += self._build_indicator_section(indicators, current_price)
        
        if history and len(history) >= 3:
            prompt += self._build_enhanced_history_section(history)
        
        if multi_timeframe:
            prompt += self._build_multi_timeframe_section(multi_timeframe)
        
        prompt += """
【最终决策检查清单】
在给出决策前，请确认：
1. 多个技术指标是否一致？ ✓/✗
2. 是否存在超买/超卖风险？ ✓/✗
3. 多时间框架是否支持此方向？ ✓/✗
4. 当前点差是否合理？ ✓/✗
5. 账户风险是否可控？ ✓/✗
6. 当前品种持仓是否已过度集中？ ✓/✗

只有以上6项检查至少4项通过时，才可发出BUY/SELL信号。否则选择HOLD。

请综合考虑市场数据、技术分析和实时账户状况，给出最终决策："""
        return prompt
    
    def _build_indicator_section(self, indicators: Dict, current_price: float) -> str:
        """构建技术指标分析部分"""
        rsi = indicators.get('rsi', 50)
        macd_main = indicators.get('macd_main', 0)
        macd_signal = indicators.get('macd_signal', 0)
        ema50 = indicators.get('ema50', 0)
        
        rsi_status = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
        macd_histogram = macd_main - macd_signal
        macd_status = "牛叉" if macd_histogram > 0 else "死叉" if macd_histogram < 0 else "中性"
        
        return f"""
【技术指标分析】
- RSI(14): {rsi:.1f} ({rsi_status})
- MACD主: {macd_main:.4f} | 信号: {macd_signal:.4f} | 柱状图: {macd_histogram:.4f}
- MACD状态: {macd_status}
- EMA50: {ema50}
- 价格 vs EMA50: {'高于' if current_price > ema50 else '低于'} ({abs(current_price - ema50):.4f})
"""
    
    def _build_history_section(self, history: List[Dict]) -> str:
        """构建历史数据分析部分"""
        recent = history[0] if history else {}
        prev = history[1] if len(history) > 1 else {}
        
        recent_trend = "上涨" if recent.get('close', 0) > recent.get('open', 0) else "下跌"
        prev_trend = "上涨" if prev.get('close', 0) > prev.get('open', 0) else "下跌"
        
        return f"""
【近期K线分析】
- 最新K线: 开={recent.get('open',0):.4f} 收={recent.get('close',0):.4f} ({recent_trend})
- 前一根K线: 收={prev.get('close',0):.4f} ({prev_trend})
"""
    
    def _build_enhanced_history_section(self, history: List[Dict]) -> str:
        """构建增强的历史数据分析部分"""
        if not history or len(history) < 5:
            return self._build_history_section(history)
        
        try:
            # 分析最近5根K线
            recent_prices = [h.get('close', 0) for h in history[:5]]
            opens = [h.get('open', 0) for h in history[:5]]
            highs = [h.get('high', 0) for h in history[:5]]
            lows = [h.get('low', 0) for h in history[:5]]
            
            # 计算趋势方向
            price_changes = []
            for i in range(1, len(recent_prices)):
                if recent_prices[i-1] > 0:
                    change = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1] * 100
                    price_changes.append(change)
            
            avg_change = sum(price_changes) / len(price_changes) if price_changes else 0
            trend = "上涨" if avg_change > 0.05 else "下跌" if avg_change < -0.05 else "震荡"
            
            # 计算波动率（ATR近似）
            true_ranges = []
            for i in range(1, len(recent_prices)):
                high_low = highs[i] - lows[i]
                high_close = abs(highs[i] - recent_prices[i-1])
                low_close = abs(lows[i] - recent_prices[i-1])
                true_range = max(high_low, high_close, low_close)
                if true_range > 0:
                    true_ranges.append(true_range)
            
            avg_true_range = sum(true_ranges) / len(true_ranges) if true_ranges else 0
            volatility = "高" if avg_true_range > recent_prices[0] * 0.002 else "中等" if avg_true_range > recent_prices[0] * 0.001 else "低"
            
            # 识别支撑阻力位（简化版）
            recent_high = max(highs[:3]) if len(highs) >= 3 else max(highs) if highs else 0
            recent_low = min(lows[:3]) if len(lows) >= 3 else min(lows) if lows else 0
            
            # 分析K线形态
            bullish_patterns = []
            bearish_patterns = []
            
            # 检查看涨吞没形态
            if len(history) >= 2:
                recent_bar = history[0]
                prev_bar = history[1]
                if (recent_bar.get('close', 0) > recent_bar.get('open', 0) and  # 最新阳线
                    prev_bar.get('close', 0) < prev_bar.get('open', 0) and      # 前一根阴线
                    recent_bar.get('open', 0) < prev_bar.get('close', 0) and    # 阳线开盘低于阴线收盘
                    recent_bar.get('close', 0) > prev_bar.get('open', 0)):      # 阳线收盘高于阴线开盘
                    bullish_patterns.append("看涨吞没形态")
            
            # 检查看跌吞没形态
            if len(history) >= 2:
                recent_bar = history[0]
                prev_bar = history[1]
                if (recent_bar.get('close', 0) < recent_bar.get('open', 0) and  # 最新阴线
                    prev_bar.get('close', 0) > prev_bar.get('open', 0) and      # 前一根阳线
                    recent_bar.get('open', 0) > prev_bar.get('close', 0) and    # 阴线开盘高于阳线收盘
                    recent_bar.get('close', 0) < prev_bar.get('open', 0)):      # 阴线收盘低于阳线开盘
                    bearish_patterns.append("看跌吞没形态")
            
            # 检查锤子线/上吊线
            if len(history) >= 1:
                recent_bar = history[0]
                bar_range = recent_bar.get('high', 0) - recent_bar.get('low', 0)
                if bar_range > 0:
                    lower_shadow = min(recent_bar.get('close', 0), recent_bar.get('open', 0)) - recent_bar.get('low', 0)
                    upper_shadow = recent_bar.get('high', 0) - max(recent_bar.get('close', 0), recent_bar.get('open', 0))
                    body = abs(recent_bar.get('close', 0) - recent_bar.get('open', 0))
                    
                    if lower_shadow > 2 * body and upper_shadow < body * 0.3:
                        if recent_bar.get('close', 0) > recent_bar.get('open', 0):
                            bullish_patterns.append("锤子线")
                        else:
                            bearish_patterns.append("上吊线")
            
            # 构建分析结果
            pattern_analysis = ""
            if bullish_patterns:
                pattern_analysis = f"看涨形态: {', '.join(bullish_patterns)}"
            elif bearish_patterns:
                pattern_analysis = f"看跌形态: {', '.join(bearish_patterns)}"
            else:
                pattern_analysis = "无明显K线形态"
            
            return f"""
【增强历史分析】
- 短期趋势: {trend} (平均变化: {avg_change:.3f}%)
- 市场波动率: {volatility} (平均真实波幅: {avg_true_range:.5f})
- 近期阻力位: {recent_high:.5f}
- 近期支撑位: {recent_low:.5f}
- K线形态: {pattern_analysis}
- 价格序列: {', '.join(f'{p:.5f}' for p in recent_prices[:3])}...
"""
        except Exception as e:
            logger.warning(f"[WARN]  增强历史分析失败: {str(e)}，使用基础分析")
            return self._build_history_section(history)
    
    def _build_multi_timeframe_section(self, multi_timeframe: Dict[str, Any]) -> str:
        """构建多时间框架分析部分 - V3.1增强版"""
        if not multi_timeframe:
            return ""
        
        section = "\n【多时间框架分析】\n"
        
        timeframe_names = {
            'h1': '1小时(短线)',
            'h4': '4小时(中线)',
            'd1': '日线(趋势)'
        }
        # 时间框架重要性权重
        timeframe_importance = {'h1': '短期信号', 'h4': '中期确认', 'd1': '长期趋势'}
        
        all_tf_signals = {}  # 记录各时间框架综合判断
        
        for timeframe in ['h1', 'h4', 'd1']:
            if timeframe not in multi_timeframe:
                continue
                
            tf_data = multi_timeframe[timeframe]
            indicators = tf_data.get('indicators', {})
            
            # 获取关键指标
            rsi = indicators.get('rsi', 50)
            macd_main = indicators.get('macd_main', 0)
            macd_signal = indicators.get('macd_signal', 0)
            macd_histogram = macd_main - macd_signal
            ema20 = indicators.get('ema20', 0)
            ema50 = indicators.get('ema50', 0)
            price = tf_data.get('price', 0)
            
            # 更精细的RSI状态
            if rsi > 80:
                rsi_status = "极度超买"
            elif rsi > 70:
                rsi_status = "超买"
            elif rsi > 60:
                rsi_status = "偏强"
            elif rsi < 20:
                rsi_status = "极度超卖"
            elif rsi < 30:
                rsi_status = "超卖"
            elif rsi < 40:
                rsi_status = "偏弱"
            else:
                rsi_status = "中性"
            
            # MACD状态（更精细）
            if macd_histogram > 0:
                if macd_histogram > abs(macd_main) * 0.5:
                    macd_status = "强看涨(柱体放大)"
                else:
                    macd_status = "看涨(柱体缩小)"
                macd_dir = "BUY"
            elif macd_histogram < 0:
                if abs(macd_histogram) > abs(macd_main) * 0.5:
                    macd_status = "强看跌(柱体放大)"
                else:
                    macd_status = "看跌(柱体缩小)"
                macd_dir = "SELL"
            else:
                macd_status = "中性"
                macd_dir = "HOLD"
            
            # EMA趋势判断
            ema_trend = ""
            if ema20 > 0 and ema50 > 0:
                if price > ema20 > ema50:
                    ema_trend = "多头排列↑"
                    ema_signal = "BUY"
                elif price < ema20 < ema50:
                    ema_trend = "空头排列↓"
                    ema_signal = "SELL"
                else:
                    ema_trend = "交叉区域↔"
                    ema_signal = "HOLD"
            else:
                ema_trend = "数据不足"
                ema_signal = "HOLD"
            
            # 综合该时间框架信号（至少2/3指标一致才算）
            signals = [macd_dir, ema_signal]
            bullish = sum(1 for s in signals if s == "BUY")
            bearish = sum(1 for s in signals if s == "SELL")
            
            if bullish >= 1 and bearish == 0 and rsi < 70:
                tf_signal = "BUY"
            elif bearish >= 1 and bullish == 0 and rsi > 30:
                tf_signal = "SELL"
            else:
                tf_signal = "HOLD"
            
            all_tf_signals[timeframe] = tf_signal
            
            section += f"- {timeframe_names.get(timeframe, timeframe)} [{timeframe_importance[timeframe]}]: 信号={tf_signal}, RSI={rsi:.1f}({rsi_status}), MACD={macd_status}, EMA={ema_trend}\n"
        
        # 多时间框架一致性分析
        bullish_count = sum(1 for s in all_tf_signals.values() if s == "BUY")
        bearish_count = sum(1 for s in all_tf_signals.values() if s == "SELL")
        neutral_count = sum(1 for s in all_tf_signals.values() if s == "HOLD")
        total = len(all_tf_signals)
        
        if total > 0:
            if bullish_count == total:
                consistency = "★★★ 强看涨一致（所有周期共振）"
            elif bearish_count == total:
                consistency = "★★★ 强看跌一致（所有周期共振）"
            elif bullish_count >= total * 0.66:
                consistency = "★★ 偏多看涨（大部分周期支持）"
            elif bearish_count >= total * 0.66:
                consistency = "★★ 偏空看跌（大部分周期支持）"
            elif bullish_count > bearish_count:
                consistency = "★ 弱偏多（仅短期看涨）"
            elif bearish_count > bullish_count:
                consistency = "★ 弱偏空（仅短期看跌）"
            else:
                consistency = "✗ 多空分歧（方向不明）"
            
            section += f"\n多时间框架共振分析: {consistency} (BUY:{bullish_count} SELL:{bearish_count} HOLD:{neutral_count})\n"
            
            # 交易建议
            if bullish_count == total:
                section += "→ 建议: 三个周期完全一致看涨，这是高概率交易信号\n"
            elif bearish_count == total:
                section += "→ 建议: 三个周期完全一致看跌，这是高概率交易信号\n"
            elif neutral_count >= 2:
                section += "→ 建议: 多个周期方向不明，强烈建议HOLD观望\n"
            elif bullish_count > bearish_count and bullish_count >= 2:
                section += "→ 建议: 多数周期看涨，可考虑谨慎BUY（注意设置止损）\n"
            elif bearish_count > bullish_count and bearish_count >= 2:
                section += "→ 建议: 多数周期看跌，可考虑谨慎SELL（注意设置止损）\n"
            else:
                section += "→ 建议: 周期信号分歧，建议HOLD等待方向明确\n"
        
        return section
    
    def call_api(self, prompt: str) -> Optional[Dict[str, Any]]:
        """调用DeepSeek API"""
        if not self.is_deepseek_available():
            logger.warning(f"[WARN]  DeepSeek不可用: {self.get_deepseek_status()}")
            return None
        
        logger.info("📡 正在调用DeepSeek API...")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是专业量化交易分析师。严格遵循层次化决策规则：优先考虑风险，多指标一致才可交易。只返回纯JSON，格式：{\"action\":\"BUY/SELL/HOLD\",\"confidence\":0.0-1.0,\"reason\":\"分析原因\"}。绝不输出JSON以外的内容。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,  # 降低温度使输出更稳定一致
            "max_tokens": 300    # 减少token，只需要简洁JSON
        }
        
        try:
            response = self.http_client.post(
                self.api_url,
                json_payload=payload,
                headers=headers
            )
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            logger.debug(f"📤 AI原始响应: {content[:200]}...")
            
            parsed = self._extract_json(content)
            if parsed:
                logger.info("[OK] AI响应解析成功")
                return parsed
            
            logger.warning("[WARN]  JSON解析失败，返回默认HOLD")
            return {
                "action": "HOLD",
                "confidence": 0.5,
                "reason": "AI响应解析失败"
            }
            
        except Exception as e:
            logger.error(f"[ERR] API调用失败: {str(e)}")
            return None
    
    def _extract_json(self, content: str) -> Optional[Dict]:
        """更健壮的JSON提取"""
        content = content.strip()
        
        first_brace = content.find('{')
        last_brace = content.rfind('}')
        
        if first_brace != -1 and last_brace > first_brace:
            json_str = content[first_brace:last_brace+1]
            return self._parse_json_string(json_str)
        
        # 多行提取策略
        lines = content.split('\n')
        buffer = []
        brace_count = 0
        in_json = False
        
        for line in lines:
            if '{' in line and not in_json:
                in_json = True
                brace_count = 0
            
            if in_json:
                buffer.append(line)
                brace_count += line.count('{')
                brace_count -= line.count('}')
                
                if brace_count == 0:
                    result = self._parse_json_string('\n'.join(buffer))
                    if result:
                        return result
                    buffer = []
                    in_json = False
        
        return None
    
    def _parse_json_string(self, json_str: str) -> Optional[Dict]:
        """解析JSON字符串"""
        try:
            data = json.loads(json_str)
            
            action = data.get('action', 'HOLD').upper()
            if action not in ['BUY', 'SELL', 'HOLD']:
                action = 'HOLD'
            
            try:
                confidence = float(data.get('confidence', 0.5))
            except (ValueError, TypeError):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))
            
            reason = str(data.get('reason', ''))[:200]
            
            # 解析止损止盈pips（范围与提示词一致：SL=25-150pips，TP=40-300pips）
            stop_loss_pips = data.get('stop_loss_pips')
            if stop_loss_pips is not None:
                try:
                    stop_loss_pips = int(float(stop_loss_pips))
                    stop_loss_pips = max(25, min(150, stop_loss_pips))  # 最小25pips防止invalid stops
                    logger.debug(f"[SL/TP] 解析AI止损: {stop_loss_pips}pips (${stop_loss_pips*0.1:.1f})")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[WARN]  AI止损pips解析失败 ({stop_loss_pips!r}): {e}")
                    stop_loss_pips = None
            
            take_profit_pips = data.get('take_profit_pips')
            if take_profit_pips is not None:
                try:
                    take_profit_pips = int(float(take_profit_pips))
                    take_profit_pips = max(40, min(300, take_profit_pips))  # 最小40pips，确保盈亏比
                    logger.debug(f"[SL/TP] 解析AI止盈: {take_profit_pips}pips (${take_profit_pips*0.1:.1f})")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[WARN]  AI止盈pips解析失败 ({take_profit_pips!r}): {e}")
                    take_profit_pips = None
            
            result = {
                "action": action,
                "confidence": confidence,
                "reason": reason
            }
            
            # 只有当有值时才添加
            if stop_loss_pips is not None:
                result["stop_loss_pips"] = stop_loss_pips
            if take_profit_pips is not None:
                result["take_profit_pips"] = take_profit_pips
            
            return result
        except json.JSONDecodeError:
            return None
    
    def get_fallback_strategy(self, symbol: str = "", bid: float = 0.0, ask: float = 0.0,
                             indicators: Optional[Dict[str, Any]] = None,
                             multi_timeframe: Optional[Dict[str, Any]] = None) -> Tuple[str, float, str]:
        """
        后备策略 - 智能策略（优先）或随机策略（备选）
        
        参数:
            symbol: 交易品种
            bid: 买入价
            ask: 卖出价
            indicators: 技术指标数据
        
        返回:
            (action, confidence, reason)
        """
        # 如果有指标数据，使用智能策略
        if indicators is not None:
            return self._get_smart_fallback_strategy(symbol, bid, ask, indicators, multi_timeframe)
        
        # 否则使用安全的保守策略（无可交易信号时返回HOLD）
        # 注意：无指标数据时不应产生虚假的交易信号
        logger.warning("[WARN]  无指标数据，返回保守HOLD（防止随机信号触发实盘交易）")
        return "HOLD", 0.1, "安全策略: 无指标数据，不具备交易条件"
    
    def _get_smart_fallback_strategy(self, symbol: str, bid: float, ask: float,
                                    indicators: Dict[str, Any],
                                    multi_timeframe: Optional[Dict[str, Any]] = None) -> Tuple[str, float, str]:
        """
        智能后备策略 - 基于技术指标和市场数据的决策
        
        算法逻辑:
        1. 分析技术指标的一致性
        2. 计算看涨/看跌信号强度
        3. 基于多个指标加权决策
        4. 设置合理的置信度
        """
        try:
            # 提取指标数据
            rsi = indicators.get('rsi', 50.0)
            macd_main = indicators.get('macd_main', 0.0)
            macd_signal = indicators.get('macd_signal', 0.0)
            ema20 = indicators.get('ema20', bid)
            ema50 = indicators.get('ema50', bid)
            ema100 = indicators.get('ema100', bid)
            stoch_main = indicators.get('stoch_main', 50.0)
            stoch_signal = indicators.get('stoch_signal', 50.0)
            
            current_price = (bid + ask) / 2
            spread = ask - bid
            
            # 计算看涨/看跌信号分数
            bullish_score = 0
            bearish_score = 0
            
            # 1. RSI分析
            if rsi < 35:
                bullish_score += 2  # 超卖区域，强烈看涨
            elif rsi > 65:
                bearish_score += 2  # 超买区域，强烈看跌
            elif rsi < 45:
                bullish_score += 1  # 偏超卖，弱看涨
            elif rsi > 55:
                bearish_score += 1  # 偏超买，弱看跌
            
            # 2. MACD分析
            macd_histogram = macd_main - macd_signal
            if macd_main > 0 and macd_histogram > 0:
                bullish_score += 3  # 强烈看涨
            elif macd_main < 0 and macd_histogram < 0:
                bearish_score += 3  # 强烈看跌
            elif macd_histogram > 0:
                bullish_score += 1  # 弱看涨
            elif macd_histogram < 0:
                bearish_score += 1  # 弱看跌
            
            # 3. EMA排列分析
            if current_price > ema20 > ema50 > ema100:
                bullish_score += 3  # 完美多头排列
            elif current_price < ema20 < ema50 < ema100:
                bearish_score += 3  # 完美空头排列
            elif current_price > ema20 > ema50:
                bullish_score += 2  # 短期多头排列
            elif current_price < ema20 < ema50:
                bearish_score += 2  # 短期空头排列
            elif current_price > ema20:
                bullish_score += 1  # 价格在EMA20之上
            elif current_price < ema20:
                bearish_score += 1  # 价格在EMA20之下
            
            # 4. 随机指标分析
            if stoch_main < 20 and stoch_signal < 20:
                bullish_score += 2  # 双超卖
            elif stoch_main > 80 and stoch_signal > 80:
                bearish_score += 2  # 双超买
            elif stoch_main > stoch_signal and stoch_main < 50:
                bullish_score += 1  # 金叉在下方区域
            elif stoch_main < stoch_signal and stoch_main > 50:
                bearish_score += 1  # 死叉在上方区域
            
            # 5. 价格相对位置分析
            if current_price > (ema20 + ema50 + ema100) / 3:
                bullish_score += 1  # 价格在均线之上
            else:
                bearish_score += 1  # 价格在均线之下
            
            # 多时间框架分析（带动态权重）
            mtf_signals = {}  # 记录各时间框架信号
            if multi_timeframe:
                current_weights = self.weight_optimizer.get_current_weights()
                
                weighted_bullish = 0.0
                weighted_bearish = 0.0
                
                for timeframe in ['h1', 'h4', 'd1']:
                    if timeframe not in multi_timeframe:
                        continue
                        
                    tf_data = multi_timeframe[timeframe]
                    indicators_tf = tf_data.get('indicators', {})
                    
                    # 分析MACD方向
                    macd_main = indicators_tf.get('macd_main', 0)
                    macd_signal = indicators_tf.get('macd_signal', 0)
                    macd_histogram = macd_main - macd_signal
                    
                    # 获取权重
                    tf_weight = current_weights.get(timeframe, 0.33)
                    
                    # 记录时间框架信号
                    if macd_histogram > 0.0001:
                        mtf_signals[timeframe] = "BUY"
                        weighted_bullish += tf_weight * 3  # 看涨信号（加权）
                    elif macd_histogram < -0.0001:
                        mtf_signals[timeframe] = "SELL"
                        weighted_bearish += tf_weight * 3  # 看跌信号（加权）
                    else:
                        mtf_signals[timeframe] = "HOLD"
                
                # 应用权重调整到分数
                if weighted_bullish > 0 or weighted_bearish > 0:
                    # 将权重转换为整数分数
                    bullish_score += int(weighted_bullish * 2)
                    bearish_score += int(weighted_bearish * 2)
                    
                    # 记录权重信息到reason
                    reason_suffix = f"[权重: {current_weights}]"
                    if 'reason_prefix' not in locals():
                        if weighted_bullish > weighted_bearish:
                            reason_prefix = f"多时间框架看涨（加权: {weighted_bullish:.2f}）{reason_suffix}"
                        elif weighted_bearish > weighted_bullish:
                            reason_prefix = f"多时间框架看跌（加权: {weighted_bearish:.2f}）{reason_suffix}"
                        else:
                            reason_prefix = f"多时间框架分歧{reason_suffix}"
            
            # 决策逻辑
            total_signals = max(bullish_score + bearish_score, 1)  # 避免除零
            
            if bullish_score > bearish_score:
                # 看涨信号更强
                signal_strength = (bullish_score - bearish_score) / total_signals
                if signal_strength > 0.3:
                    action = "BUY"
                    confidence = min(0.5 + signal_strength, 0.85)
                    reason = f"智能后备: 看涨信号占优 (强度: {signal_strength:.2f})"
                else:
                    action = "HOLD"
                    confidence = 0.6
                    reason = "智能后备: 看涨信号不足，建议观望"
            
            elif bearish_score > bullish_score:
                # 看跌信号更强
                signal_strength = (bearish_score - bullish_score) / total_signals
                if signal_strength > 0.3:
                    action = "SELL"
                    confidence = min(0.5 + signal_strength, 0.85)
                    reason = f"智能后备: 看跌信号占优 (强度: {signal_strength:.2f})"
                else:
                    action = "HOLD"
                    confidence = 0.6
                    reason = "智能后备: 看跌信号不足，建议观望"
            
            else:
                # 信号平衡或没有明显信号
                action = "HOLD"
                confidence = 0.5
                reason = "智能后备: 多空信号平衡，市场震荡"
            
            # 最终验证：确保置信度在合理范围
            confidence = max(0.3, min(0.9, confidence))
            
            # 记录交易信号到权重优化器
            if 'mtf_signals' in locals():
                signal = TradeSignal(
                    timestamp=time.time(),
                    symbol=symbol,
                    action=action,
                    confidence=confidence,
                    bid=bid,
                    ask=ask,
                    multi_timeframe_signals=mtf_signals
                )
                self.weight_optimizer.record_signal(signal)
            
            logger.info(f"🎯 智能后备策略: {action} | 置信度: {confidence:.2f} | 原因: {reason}")
            return action, confidence, reason
            
        except Exception as e:
            logger.error(f"[ERR] 智能后备策略失败: {str(e)}，返回安全HOLD")
            # 失败时返回安全HOLD而非随机策略，避免虚假信号
            return "HOLD", 0.1, f"安全策略: 指标分析异常 ({str(e)[:50]})"
    
    def _build_account_context_section(self, symbol: str) -> str:
        """构建账户上下文部分"""
        try:
            # 获取实时MQL5数据
            realtime_data = self.mql5_data_manager.get_real_time_data_summary()
            account_data = realtime_data.get("account_summary", {})
            positions_data = realtime_data.get("positions_summary", {})
            
            # 提取关键账户信息
            balance = account_data.get("balance", 0.0)
            equity = account_data.get("equity", 0.0)
            margin_used = account_data.get("margin_used", 0.0)
            margin_free = account_data.get("margin_free", 0.0)
            margin_level = account_data.get("margin_level", 0.0)
            floating_profit = account_data.get("floating_profit", 0.0)
            
            # 计算账户健康度
            account_health = "优秀"
            if margin_level < 100.0:
                account_health = "危险 (保证金水平<100%)"
            elif margin_level < 200.0:
                account_health = "一般"
            
            # 检查当前品种的已有持仓
            symbol_positions = positions_data.get("by_symbol", {}).get(symbol, {})
            existing_position_count = symbol_positions.get("position_count", 0)
            existing_position_volume = symbol_positions.get("total_volume", 0.0)
            existing_position_profit = symbol_positions.get("total_profit", 0.0)
            
            # 检查持仓集中度
            total_position_count = positions_data.get("total_count", 0)
            total_position_volume = positions_data.get("total_volume", 0.0)
            
            concentration_ratio = 0.0
            if total_position_volume > 0:
                concentration_ratio = existing_position_volume / total_position_volume
            
            concentration_warning = ""
            if concentration_ratio > 0.5:
                concentration_warning = "[WARN]  当前品种持仓占比过高 (>50%)，建议谨慎开仓"
            elif concentration_ratio > 0.3:
                concentration_warning = "[WARN]  当前品种持仓占比偏高 (>30%)，建议减少仓位"
            
            # 构建账户上下文部分
            account_section = f"""
【账户实时状态 - 基于MQL5真实数据】
- 账户余额: ${balance:.2f}
- 账户净值: ${equity:.2f} (浮动盈亏: ${floating_profit:.2f})
- 保证金使用: ${margin_used:.2f} (可用保证金: ${margin_free:.2f})
- 保证金水平: {margin_level:.1f}% (账户健康度: {account_health})
- 总持仓数量: {total_position_count}个 (总手数: {total_position_volume:.2f})
"""
            
            # 添加当前品种持仓信息
            if existing_position_count > 0:
                account_section += f"- 当前品种({symbol})已有持仓: {existing_position_count}个 (手数: {existing_position_volume:.2f}, 盈亏: ${existing_position_profit:.2f})\n"
                account_section += f"- 持仓集中度: {concentration_ratio:.1%} {concentration_warning}\n"
            else:
                account_section += f"- 当前品种({symbol})无持仓，可自由开仓\n"
            
            # 添加风险提示
            if margin_level < 100.0:
                account_section += "[WARN]  警告: 保证金水平过低，强烈建议HOLD或减少仓位\n"
            elif margin_level < 200.0:
                account_section += "[WARN]  提示: 保证金水平一般，建议保守交易\n"
            
            return account_section
            
        except Exception as e:
            logger.error(f"[ERR] 构建账户上下文失败: {str(e)}")
            # 返回基本的账户上下文提示
            return """
【账户实时状态 - 数据获取失败】
注意: 实时账户数据获取失败，决策时请考虑账户风险控制。
建议: 如不确定账户状况，优先选择HOLD观望。
"""
