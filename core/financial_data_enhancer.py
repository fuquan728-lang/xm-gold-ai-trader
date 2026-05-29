#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融数据增强器
集成外部金融数据源增强AI分析
"""

import json
import os
import asyncio
import subprocess
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import aiohttp
from .logger import logger
from .cache import global_cache


@dataclass
class FinancialData:
    """金融数据结构"""
    symbol: str
    data_type: str
    data: Dict[str, Any]
    timestamp: datetime
    source: str
    confidence: float = 0.8


@dataclass
class EnhancedAnalysis:
    """增强分析结果"""
    base_analysis: Dict[str, Any]
    financial_data: List[FinancialData]
    decision_impact: Dict[str, Any]
    final_decision: Dict[str, Any]


class FinancialDataEnhancer:
    """
    金融数据增强器 - 集成外部数据源
    """
    
    def __init__(self):
        self.cache_duration = 300  # 5分钟缓存
        self.neodata_script_path = None
        self._find_neodata_script()
        
        # 数据源权重
        self.data_source_weights = {
            "market_sentiment": 0.3,
            "money_flow": 0.25,
            "macro_economic": 0.2,
            "sector_heat": 0.15,
            "news_sentiment": 0.1
        }
        
        # 缓存
        self.data_cache = {}
    
    def _find_neodata_script(self):
        """查找NeoData查询脚本"""
        # 查找可能的路径
        possible_paths = [
            os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins", "marketplaces", 
                        "cb_teams_marketplace", "plugins", "finance-data", "skills", 
                        "neodata-financial-search", "scripts", "query.py"),
            os.path.join(os.path.expanduser("~"), ".workbuddy", "plugins", "marketplaces", 
                        "codebuddy-plugins-official", "external_plugins", "finance-data-retrieval",
                        "scripts", "query.py"),
            "scripts/query.py",
            "neodata/query.py"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self.neodata_script_path = path
                logger.info(f"找到NeoData脚本: {path}")
                break
        
        if not self.neodata_script_path:
            logger.warning("未找到NeoData查询脚本，金融数据增强功能将受限")
    
    async def enhance_analysis(self, symbol: str, base_analysis: Dict[str, Any],
                              market_state: str, account_context: Dict) -> EnhancedAnalysis:
        """
        增强AI分析结果
        """
        logger.info(f"开始增强分析: {symbol}, 市场状态: {market_state}")
        
        financial_data = []
        
        try:
            # 1. 获取市场情绪数据
            market_sentiment = await self._get_market_sentiment(symbol, market_state)
            if market_sentiment:
                financial_data.append(market_sentiment)
            
            # 2. 获取资金流向数据
            money_flow = await self._get_money_flow(symbol)
            if money_flow:
                financial_data.append(money_flow)
            
            # 3. 获取宏观经济数据
            macro_data = await self._get_macro_economic_data()
            if macro_data:
                financial_data.append(macro_data)
            
            # 4. 获取板块热度数据
            sector_heat = await self._get_sector_heat(symbol)
            if sector_heat:
                financial_data.append(sector_heat)
            
            # 5. 获取新闻情绪数据
            news_sentiment = await self._get_news_sentiment(symbol)
            if news_sentiment:
                financial_data.append(news_sentiment)
            
            # 6. 分析数据对决策的影响
            decision_impact = self._analyze_decision_impact(
                base_analysis, financial_data, market_state, account_context
            )
            
            # 7. 生成最终决策
            final_decision = self._generate_final_decision(
                base_analysis, decision_impact, market_state
            )
            
            enhanced = EnhancedAnalysis(
                base_analysis=base_analysis,
                financial_data=financial_data,
                decision_impact=decision_impact,
                final_decision=final_decision
            )
            
            logger.info(f"增强分析完成: {symbol}, 获取{len(financial_data)}个数据源")
            return enhanced
            
        except Exception as e:
            logger.error(f"增强分析失败: {e}")
            # 返回基础分析
            return EnhancedAnalysis(
                base_analysis=base_analysis,
                financial_data=[],
                decision_impact={"error": str(e), "impact_level": "NONE"},
                final_decision=base_analysis
            )
    
    async def _get_market_sentiment(self, symbol: str, market_state: str) -> Optional[FinancialData]:
        """获取市场情绪数据"""
        cache_key = f"market_sentiment_{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        
        if cache_key in self.data_cache:
            cached_data = self.data_cache[cache_key]
            if datetime.now() - cached_data.timestamp < timedelta(minutes=30):
                return cached_data
        
        try:
            # 使用NeoData查询市场情绪
            query = f"{symbol} 市场情绪 资金流向"
            result = await self._query_neodata(query)
            
            if result and "apiData" in result:
                api_data = result["apiData"]
                
                # 解析市场情绪数据
                sentiment_data = self._parse_market_sentiment(api_data, symbol)
                
                if sentiment_data:
                    data = FinancialData(
                        symbol=symbol,
                        data_type="market_sentiment",
                        data=sentiment_data,
                        timestamp=datetime.now(),
                        source="neodata",
                        confidence=0.8
                    )
                    
                    self.data_cache[cache_key] = data
                    return data
        
        except Exception as e:
            logger.warning(f"获取市场情绪失败: {e}")
        
        return None
    
    async def _get_money_flow(self, symbol: str) -> Optional[FinancialData]:
        """获取资金流向数据"""
        cache_key = f"money_flow_{symbol}_{datetime.now().strftime('%Y%m%d')}"
        
        if cache_key in self.data_cache:
            cached_data = self.data_cache[cache_key]
            if datetime.now() - cached_data.timestamp < timedelta(hours=1):
                return cached_data
        
        try:
            # 使用NeoData查询资金流向
            query = f"{symbol} 资金流向 主力资金"
            result = await self._query_neodata(query)
            
            if result and "apiData" in result:
                api_data = result["apiData"]
                
                # 解析资金流向数据
                money_flow_data = self._parse_money_flow(api_data, symbol)
                
                if money_flow_data:
                    data = FinancialData(
                        symbol=symbol,
                        data_type="money_flow",
                        data=money_flow_data,
                        timestamp=datetime.now(),
                        source="neodata",
                        confidence=0.85
                    )
                    
                    self.data_cache[cache_key] = data
                    return data
        
        except Exception as e:
            logger.warning(f"获取资金流向失败: {e}")
        
        return None
    
    async def _get_macro_economic_data(self) -> Optional[FinancialData]:
        """获取宏观经济数据"""
        cache_key = f"macro_economic_{datetime.now().strftime('%Y%m%d')}"
        
        if cache_key in self.data_cache:
            cached_data = self.data_cache[cache_key]
            if datetime.now() - cached_data.timestamp < timedelta(hours=3):
                return cached_data
        
        try:
            # 使用NeoData查询宏观经济
            query = "中国最新CPI GDP 利率"
            result = await self._query_neodata(query)
            
            if result and "apiData" in result:
                api_data = result["apiData"]
                
                # 解析宏观经济数据
                macro_data = self._parse_macro_economic(api_data)
                
                if macro_data:
                    data = FinancialData(
                        symbol="CN",
                        data_type="macro_economic",
                        data=macro_data,
                        timestamp=datetime.now(),
                        source="neodata",
                        confidence=0.9
                    )
                    
                    self.data_cache[cache_key] = data
                    return data
        
        except Exception as e:
            logger.warning(f"获取宏观经济数据失败: {e}")
        
        return None
    
    async def _get_sector_heat(self, symbol: str) -> Optional[FinancialData]:
        """获取板块热度数据"""
        cache_key = f"sector_heat_{symbol}_{datetime.now().strftime('%Y%m%d')}"
        
        if cache_key in self.data_cache:
            cached_data = self.data_cache[cache_key]
            if datetime.now() - cached_data.timestamp < timedelta(minutes=30):
                return cached_data
        
        try:
            # 使用NeoData查询板块热度
            query = f"{symbol} 所属板块 热度"
            result = await self._query_neodata(query)
            
            if result and "apiData" in result:
                api_data = result["apiData"]
                
                # 解析板块热度数据
                sector_data = self._parse_sector_heat(api_data, symbol)
                
                if sector_data:
                    data = FinancialData(
                        symbol=symbol,
                        data_type="sector_heat",
                        data=sector_data,
                        timestamp=datetime.now(),
                        source="neodata",
                        confidence=0.75
                    )
                    
                    self.data_cache[cache_key] = data
                    return data
        
        except Exception as e:
            logger.warning(f"获取板块热度失败: {e}")
        
        return None
    
    async def _get_news_sentiment(self, symbol: str) -> Optional[FinancialData]:
        """获取新闻情绪数据"""
        cache_key = f"news_sentiment_{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        
        if cache_key in self.data_cache:
            cached_data = self.data_cache[cache_key]
            if datetime.now() - cached_data.timestamp < timedelta(minutes=15):
                return cached_data
        
        try:
            # 使用NeoData查询新闻情绪
            query = f"{symbol} 最新新闻 市场情绪"
            result = await self._query_neodata(query, data_type="doc")
            
            if result and "docData" in result:
                doc_data = result["docData"]
                
                # 解析新闻情绪数据
                news_data = self._parse_news_sentiment(doc_data, symbol)
                
                if news_data:
                    data = FinancialData(
                        symbol=symbol,
                        data_type="news_sentiment",
                        data=news_data,
                        timestamp=datetime.now(),
                        source="neodata",
                        confidence=0.7
                    )
                    
                    self.data_cache[cache_key] = data
                    return data
        
        except Exception as e:
            logger.warning(f"获取新闻情绪失败: {e}")
        
        return None
    
    async def _query_neodata(self, query: str, data_type: str = "all") -> Optional[Dict]:
        """查询NeoData API"""
        if not self.neodata_script_path:
            logger.warning("NeoData脚本未找到，无法查询")
            return None
        
        try:
            # 执行查询脚本
            cmd = [
                "python", self.neodata_script_path,
                "--query", query,
                "--data-type", data_type
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                result_text = stdout.decode('utf-8').strip()
                try:
                    result = json.loads(result_text)
                    return result
                except json.JSONDecodeError:
                    logger.error(f"解析NeoData响应失败: {result_text[:100]}")
            else:
                error_text = stderr.decode('utf-8').strip()
                logger.error(f"NeoData查询失败: {error_text}")
        
        except Exception as e:
            logger.error(f"执行NeoData查询失败: {e}")
        
        return None
    
    def _parse_market_sentiment(self, api_data: Dict, symbol: str) -> Dict[str, Any]:
        """解析市场情绪数据"""
        sentiment_data = {
            "symbol": symbol,
            "overall_sentiment": 0.5,  # 中性
            "bullish_signals": 0,
            "bearish_signals": 0,
            "volume_trend": "neutral",
            "volatility_level": "medium"
        }
        
        try:
            # 解析apiRecall数据
            api_recall = api_data.get("apiRecall", [])
            
            for recall_item in api_recall:
                item_type = recall_item.get("type", "")
                content = recall_item.get("content", {})
                
                if item_type == "basic_info":
                    # 解析基础信息中的情绪指标
                    price_change = content.get("price_change_pct", 0)
                    volume_ratio = content.get("volume_ratio", 1.0)
                    
                    # 根据价格变化判断情绪
                    if price_change > 2:
                        sentiment_data["overall_sentiment"] = 0.8
                        sentiment_data["bullish_signals"] += 1
                    elif price_change < -2:
                        sentiment_data["overall_sentiment"] = 0.2
                        sentiment_data["bearish_signals"] += 1
                    
                    # 根据成交量判断趋势
                    if volume_ratio > 1.5:
                        sentiment_data["volume_trend"] = "strong"
                    elif volume_ratio > 1.0:
                        sentiment_data["volume_trend"] = "positive"
                    elif volume_ratio < 0.7:
                        sentiment_data["volume_trend"] = "weak"
        
        except Exception as e:
            logger.warning(f"解析市场情绪数据失败: {e}")
        
        return sentiment_data
    
    def _parse_money_flow(self, api_data: Dict, symbol: str) -> Dict[str, Any]:
        """解析资金流向数据"""
        money_flow_data = {
            "symbol": symbol,
            "main_inflow": 0,
            "main_outflow": 0,
            "retail_inflow": 0,
            "retail_outflow": 0,
            "net_inflow": 0,
            "direction": "neutral",
            "strength": "medium"
        }
        
        try:
            api_recall = api_data.get("apiRecall", [])
            
            for recall_item in api_recall:
                item_type = recall_item.get("type", "")
                content = recall_item.get("content", {})
                
                if item_type in ["fund_history", "fund_aggregation"]:
                    # 解析资金数据
                    main_inflow = content.get("main_inflow", 0)
                    main_outflow = content.get("main_outflow", 0)
                    
                    if main_inflow and main_outflow:
                        money_flow_data["main_inflow"] = main_inflow
                        money_flow_data["main_outflow"] = main_outflow
                        money_flow_data["net_inflow"] = main_inflow - main_outflow
                        
                        # 判断方向
                        if money_flow_data["net_inflow"] > 0:
                            money_flow_data["direction"] = "inflow"
                            # 判断强度
                            if abs(money_flow_data["net_inflow"]) > 100000000:  # 1亿
                                money_flow_data["strength"] = "strong"
                            elif abs(money_flow_data["net_inflow"]) > 10000000:  # 1千万
                                money_flow_data["strength"] = "medium"
                            else:
                                money_flow_data["strength"] = "weak"
                        elif money_flow_data["net_inflow"] < 0:
                            money_flow_data["direction"] = "outflow"
                            # 判断强度
                            if abs(money_flow_data["net_inflow"]) > 100000000:
                                money_flow_data["strength"] = "strong"
                            elif abs(money_flow_data["net_inflow"]) > 10000000:
                                money_flow_data["strength"] = "medium"
                            else:
                                money_flow_data["strength"] = "weak"
        
        except Exception as e:
            logger.warning(f"解析资金流向数据失败: {e}")
        
        return money_flow_data
    
    def _parse_macro_economic(self, api_data: Dict) -> Dict[str, Any]:
        """解析宏观经济数据"""
        macro_data = {
            "cpi": 0,
            "cpi_trend": "stable",
            "gdp_growth": 0,
            "gdp_trend": "stable",
            "interest_rate": 0,
            "rate_trend": "stable",
            "overall_outlook": "neutral"
        }
        
        try:
            api_recall = api_data.get("apiRecall", [])
            
            for recall_item in api_recall:
                item_type = recall_item.get("type", "")
                content = recall_item.get("content", {})
                
                if "cpi" in str(content).lower():
                    # 尝试提取CPI数据
                    macro_data["cpi"] = content.get("value", 0)
                    prev_value = content.get("prev_value", 0)
                    
                    if macro_data["cpi"] > prev_value:
                        macro_data["cpi_trend"] = "rising"
                    elif macro_data["cpi"] < prev_value:
                        macro_data["cpi_trend"] = "falling"
                
                elif "gdp" in str(content).lower():
                    # 尝试提取GDP数据
                    macro_data["gdp_growth"] = content.get("growth_rate", 0)
                    prev_growth = content.get("prev_growth", 0)
                    
                    if macro_data["gdp_growth"] > prev_growth:
                        macro_data["gdp_trend"] = "improving"
                    elif macro_data["gdp_growth"] < prev_growth:
                        macro_data["gdp_trend"] = "slowing"
        
        except Exception as e:
            logger.warning(f"解析宏观经济数据失败: {e}")
        
        return macro_data
    
    def _parse_sector_heat(self, api_data: Dict, symbol: str) -> Dict[str, Any]:
        """解析板块热度数据"""
        sector_data = {
            "symbol": symbol,
            "sector_name": "",
            "heat_index": 0,
            "rank_in_sector": 0,
            "sector_performance": "neutral",
            "leading_stocks": []
        }
        
        try:
            api_recall = api_data.get("apiRecall", [])
            
            for recall_item in api_recall:
                item_type = recall_item.get("type", "")
                content = recall_item.get("content", {})
                
                if item_type == "plate_stock_info":
                    sector_data["sector_name"] = content.get("plate_name", "")
                    sector_data["heat_index"] = content.get("heat_index", 0)
                    sector_data["rank_in_sector"] = content.get("rank", 0)
                    
                    # 获取龙头股
                    leading_stocks = content.get("leading_stocks", [])
                    if isinstance(leading_stocks, list):
                        sector_data["leading_stocks"] = leading_stocks[:5]  # 前5个
        
        except Exception as e:
            logger.warning(f"解析板块热度数据失败: {e}")
        
        return sector_data
    
    def _parse_news_sentiment(self, doc_data: Dict, symbol: str) -> Dict[str, Any]:
        """解析新闻情绪数据"""
        news_data = {
            "symbol": symbol,
            "recent_news_count": 0,
            "positive_news": 0,
            "negative_news": 0,
            "neutral_news": 0,
            "overall_sentiment": 0.5,
            "key_topics": []
        }
        
        try:
            doc_recall = doc_data.get("docRecall", [])
            
            total_news = 0
            sentiment_score = 0
            
            for recall_group in doc_recall:
                doc_list = recall_group.get("docList", [])
                
                for doc in doc_list:
                    total_news += 1
                    
                    # 简单的关键词判断（实际应该使用情感分析）
                    title = doc.get("title", "").lower()
                    content = doc.get("content", "").lower()
                    
                    positive_keywords = ["上涨", "利好", "增长", "突破", "创新高", "买入", "推荐"]
                    negative_keywords = ["下跌", "利空", "下滑", "亏损", "卖出", "警告", "风险"]
                    
                    positive_count = sum(1 for kw in positive_keywords if kw in title or kw in content)
                    negative_count = sum(1 for kw in negative_keywords if kw in title or kw in content)
                    
                    if positive_count > negative_count:
                        news_data["positive_news"] += 1
                        sentiment_score += 0.7
                    elif negative_count > positive_count:
                        news_data["negative_news"] += 1
                        sentiment_score += 0.3
                    else:
                        news_data["neutral_news"] += 1
                        sentiment_score += 0.5
            
            if total_news > 0:
                news_data["recent_news_count"] = total_news
                news_data["overall_sentiment"] = sentiment_score / total_news
        
        except Exception as e:
            logger.warning(f"解析新闻情绪数据失败: {e}")
        
        return news_data
    
    def _analyze_decision_impact(self, base_analysis: Dict, financial_data: List[FinancialData],
                                market_state: str, account_context: Dict) -> Dict[str, Any]:
        """分析金融数据对决策的影响"""
        impact_analysis = {
            "impact_level": "NONE",  # NONE, LOW, MEDIUM, HIGH
            "impact_direction": "NEUTRAL",  # BULLISH, BEARISH, NEUTRAL
            "adjustment_factors": [],
            "confidence_adjustment": 0.0,
            "action_adjustment": None,
            "detailed_analysis": {}
        }
        
        try:
            # 初始化影响分数
            impact_score = 0
            weight_sum = 0
            
            # 分析每个数据源的影响
            for data in financial_data:
                data_type = data.data_type
                data_content = data.data
                confidence = data.confidence
                
                if data_type in self.data_source_weights:
                    weight = self.data_source_weights[data_type]
                    
                    # 分析该数据源的影响
                    data_impact = self._analyze_single_data_impact(
                        data_type, data_content, base_analysis, market_state
                    )
                    
                    if data_impact["has_impact"]:
                        impact_score += data_impact["impact_score"] * weight * confidence
                        weight_sum += weight * confidence
                        
                        # 记录详细分析
                        impact_analysis["detailed_analysis"][data_type] = {
                            "impact_score": data_impact["impact_score"],
                            "reason": data_impact["reason"],
                            "suggestion": data_impact["suggestion"]
                        }
                        
                        # 收集调整因子
                        if data_impact["suggestion"]:
                            impact_analysis["adjustment_factors"].append(
                                f"{data_type}: {data_impact['suggestion']}"
                            )
            
            # 计算总体影响
            if weight_sum > 0:
                normalized_impact = impact_score / weight_sum
                
                # 确定影响级别
                if abs(normalized_impact) > 0.3:
                    impact_analysis["impact_level"] = "HIGH"
                elif abs(normalized_impact) > 0.15:
                    impact_analysis["impact_level"] = "MEDIUM"
                elif abs(normalized_impact) > 0.05:
                    impact_analysis["impact_level"] = "LOW"
                
                # 确定影响方向
                if normalized_impact > 0.1:
                    impact_analysis["impact_direction"] = "BULLISH"
                elif normalized_impact < -0.1:
                    impact_analysis["impact_direction"] = "BEARISH"
                
                # 计算置信度调整
                if impact_analysis["impact_level"] == "HIGH":
                    impact_analysis["confidence_adjustment"] = 0.1 * (1 if normalized_impact > 0 else -1)
                elif impact_analysis["impact_level"] == "MEDIUM":
                    impact_analysis["confidence_adjustment"] = 0.05 * (1 if normalized_impact > 0 else -1)
                elif impact_analysis["impact_level"] == "LOW":
                    impact_analysis["confidence_adjustment"] = 0.02 * (1 if normalized_impact > 0 else -1)
                
                # 检查是否需要调整动作
                base_action = base_analysis.get("action", "HOLD")
                base_confidence = base_analysis.get("confidence", 0.5)
                
                # 高影响且方向相反时考虑调整动作
                if (impact_analysis["impact_level"] == "HIGH" and 
                    ((base_action == "BUY" and impact_analysis["impact_direction"] == "BEARISH") or
                     (base_action == "SELL" and impact_analysis["impact_direction"] == "BULLISH"))):
                    
                    if base_confidence < 0.7:
                        # 低置信度时调整为HOLD
                        impact_analysis["action_adjustment"] = "HOLD"
                    else:
                        # 高置信度时只调整置信度
                        impact_analysis["action_adjustment"] = "REDUCE_CONFIDENCE"
        
        except Exception as e:
            logger.error(f"分析决策影响失败: {e}")
        
        return impact_analysis
    
    def _analyze_single_data_impact(self, data_type: str, data_content: Dict,
                                   base_analysis: Dict, market_state: str) -> Dict[str, Any]:
        """分析单个数据源的影响"""
        impact_result = {
            "has_impact": False,
            "impact_score": 0.0,
            "reason": "",
            "suggestion": ""
        }
        
        base_action = base_analysis.get("action", "HOLD")
        
        try:
            if data_type == "market_sentiment":
                sentiment = data_content.get("overall_sentiment", 0.5)
                volume_trend = data_content.get("volume_trend", "neutral")
                
                # 市场情绪分析
                if sentiment > 0.7:
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] = 0.3 if base_action == "BUY" else -0.3 if base_action == "SELL" else 0
                    impact_result["reason"] = f"市场情绪积极({sentiment:.2f})"
                    impact_result["suggestion"] = "利好买入信号" if base_action == "BUY" else "不利于卖出"
                
                elif sentiment < 0.3:
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] = -0.3 if base_action == "BUY" else 0.3 if base_action == "SELL" else 0
                    impact_result["reason"] = f"市场情绪消极({sentiment:.2f})"
                    impact_result["suggestion"] = "不利于买入" if base_action == "BUY" else "利好卖出信号"
                
                # 成交量趋势
                if volume_trend == "strong" and market_state != "RANGING":
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] += 0.1
                    impact_result["reason"] += "，成交量放大"
            
            elif data_type == "money_flow":
                direction = data_content.get("direction", "neutral")
                strength = data_content.get("strength", "medium")
                
                if direction != "neutral":
                    impact_result["has_impact"] = True
                    
                    if direction == "inflow":
                        score = 0.25 if base_action == "BUY" else -0.25 if base_action == "SELL" else 0
                        impact_result["impact_score"] = score
                        impact_result["reason"] = f"资金净流入({strength})"
                        impact_result["suggestion"] = "利好价格上涨"
                    
                    elif direction == "outflow":
                        score = -0.25 if base_action == "BUY" else 0.25 if base_action == "SELL" else 0
                        impact_result["impact_score"] = score
                        impact_result["reason"] = f"资金净流出({strength})"
                        impact_result["suggestion"] = "利空价格下跌"
            
            elif data_type == "macro_economic":
                cpi_trend = data_content.get("cpi_trend", "stable")
                gdp_trend = data_content.get("gdp_trend", "stable")
                overall_outlook = data_content.get("overall_outlook", "neutral")
                
                # 宏观经济影响
                macro_score = 0
                reasons = []
                
                if cpi_trend == "rising":
                    macro_score -= 0.1  # 通胀上升对股市不利
                    reasons.append("通胀上升")
                elif cpi_trend == "falling":
                    macro_score += 0.05  # 通胀下降对股市有利
                    reasons.append("通胀下降")
                
                if gdp_trend == "improving":
                    macro_score += 0.15  # 经济增长对股市有利
                    reasons.append("经济增长")
                elif gdp_trend == "slowing":
                    macro_score -= 0.1  # 经济放缓对股市不利
                    reasons.append("经济放缓")
                
                if overall_outlook == "positive":
                    macro_score += 0.1
                    reasons.append("宏观展望积极")
                elif overall_outlook == "negative":
                    macro_score -= 0.1
                    reasons.append("宏观展望消极")
                
                if reasons:
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] = macro_score
                    impact_result["reason"] = "，".join(reasons)
                    impact_result["suggestion"] = f"宏观因素{'+利好' if macro_score > 0 else '-利空' if macro_score < 0 else '中性'}"
            
            elif data_type == "sector_heat":
                heat_index = data_content.get("heat_index", 0)
                sector_performance = data_content.get("sector_performance", "neutral")
                
                if heat_index > 70:
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] = 0.15 if base_action == "BUY" else -0.15 if base_action == "SELL" else 0
                    impact_result["reason"] = f"板块热度高({heat_index})"
                    impact_result["suggestion"] = "板块受关注，交易活跃"
                
                elif heat_index < 30:
                    impact_result["has_impact"] = True
                    impact_result["impact_score"] = -0.1 if base_action == "BUY" else 0.1 if base_action == "SELL" else 0
                    impact_result["reason"] = f"板块热度低({heat_index})"
                    impact_result["suggestion"] = "板块关注度低，流动性风险"
            
            elif data_type == "news_sentiment":
                overall_sentiment = data_content.get("overall_sentiment", 0.5)
                recent_news_count = data_content.get("recent_news_count", 0)
                
                if recent_news_count > 0:
                    impact_result["has_impact"] = True
                    
                    # 新闻情绪影响
                    if overall_sentiment > 0.7:
                        score = 0.1 if base_action == "BUY" else -0.1 if base_action == "SELL" else 0
                        impact_result["impact_score"] = score
                        impact_result["reason"] = f"新闻情绪积极({overall_sentiment:.2f})"
                        impact_result["suggestion"] = "媒体正面报道较多"
                    
                    elif overall_sentiment < 0.3:
                        score = -0.1 if base_action == "BUY" else 0.1 if base_action == "SELL" else 0
                        impact_result["impact_score"] = score
                        impact_result["reason"] = f"新闻情绪消极({overall_sentiment:.2f})"
                        impact_result["suggestion"] = "媒体负面报道较多"
        
        except Exception as e:
            logger.warning(f"分析{data_type}影响失败: {e}")
        
        return impact_result
    
    def _generate_final_decision(self, base_analysis: Dict, impact_analysis: Dict,
                                market_state: str) -> Dict[str, Any]:
        """生成最终决策"""
        final_decision = base_analysis.copy()
        
        try:
            action = base_analysis.get("action", "HOLD")
            confidence = base_analysis.get("confidence", 0.5)
            reason = base_analysis.get("reason", "")
            
            impact_level = impact_analysis.get("impact_level", "NONE")
            impact_direction = impact_analysis.get("impact_direction", "NEUTRAL")
            confidence_adjustment = impact_analysis.get("confidence_adjustment", 0.0)
            action_adjustment = impact_analysis.get("action_adjustment")
            adjustment_factors = impact_analysis.get("adjustment_factors", [])
            
            # 应用置信度调整
            adjusted_confidence = confidence + confidence_adjustment
            adjusted_confidence = max(0.0, min(1.0, adjusted_confidence))
            
            # 应用动作调整
            adjusted_action = action
            adjustment_reason = ""
            
            if action_adjustment == "HOLD":
                adjusted_action = "HOLD"
                adjustment_reason = "金融数据强烈建议观望"
            
            elif action_adjustment == "REDUCE_CONFIDENCE":
                # 只降低置信度，不改变动作
                adjusted_confidence *= 0.8
                adjustment_reason = "金融数据与当前信号矛盾，降低置信度"
            
            # 添加调整原因
            if adjustment_factors:
                if adjustment_reason:
                    adjustment_reason += "；"
                adjustment_reason += "金融数据因素: " + "；".join(adjustment_factors)
            
            # 构建最终决策
            final_decision.update({
                "action": adjusted_action,
                "confidence": round(adjusted_confidence, 3),
                "reason": reason + (" | " + adjustment_reason if adjustment_reason else ""),
                "financial_data_impact": {
                    "level": impact_level,
                    "direction": impact_direction,
                    "confidence_adjustment": round(confidence_adjustment, 3),
                    "action_adjustment": action_adjustment
                },
                "enhanced": True,
                "enhancement_timestamp": datetime.now().isoformat()
            })
        
        except Exception as e:
            logger.error(f"生成最终决策失败: {e}")
        
        return final_decision


# 单例模式
_financial_enhancer_instance = None

def get_financial_enhancer() -> FinancialDataEnhancer:
    """获取金融数据增强器实例"""
    global _financial_enhancer_instance
    if _financial_enhancer_instance is None:
        _financial_enhancer_instance = FinancialDataEnhancer()
    return _financial_enhancer_instance