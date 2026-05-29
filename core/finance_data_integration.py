#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金融数据集成模块 - 统一管理外部金融数据源

功能：
1. NeoData自然语言金融数据搜索集成
2. 多数据源管理和缓存
3. 与MT5 AI交易系统无缝集成
"""

import os
import sys
import json
import time
import logging
import subprocess
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import config
from core.logger import logger
from core.cache import global_cache


class FinanceDataIntegration:
    """金融数据集成管理器"""
    
    def __init__(self):
        """初始化金融数据集成管理器"""
        self.enabled = config.FINANCE_DATA_ENABLED
        self.neodata_enabled = config.NEODATA_ENABLED
        self.data_sources = config.EXTERNAL_DATA_SOURCES
        self.max_retries = config.MAX_EXTERNAL_RETRIES
        
        # NeoData技能路径
        self.neodata_skill_path = r"C:\Users\彩印\.workbuddy\plugins\marketplaces\cb_teams_marketplace\plugins\finance-data\skills\neodata-financial-search"
        
        # 缓存键前缀
        self.cache_prefix = "finance_data:"
        
        # 检查Python可用性
        self.python_cmd = self._detect_python()
        
        logger.info(f"[FINANCE] 金融数据集成初始化: enabled={self.enabled}, sources={self.data_sources}")
        logger.info(f"[FINANCE] Python命令: {self.python_cmd}")
    
    def _detect_python(self) -> str:
        """检测可用的Python命令"""
        # 尝试python
        try:
            result = subprocess.run(["python", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                return "python"
        except FileNotFoundError:
            pass
        
        # 尝试python3
        try:
            result = subprocess.run(["python3", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                return "python3"
        except FileNotFoundError:
            pass
        
        # 默认返回python（即使可能不存在，后续会报错）
        return "python"
    
    def is_available(self) -> bool:
        """检查金融数据集成是否可用"""
        if not self.enabled:
            return False
        
        # 检查NeoData技能路径
        if "neodata" in self.data_sources and self.neodata_enabled:
            if not os.path.exists(self.neodata_skill_path):
                logger.warning(f"[FINANCE] NeoData技能路径不存在: {self.neodata_skill_path}")
                return False
            
            # 检查query.py脚本
            query_script = os.path.join(self.neodata_skill_path, "scripts", "query.py")
            if not os.path.exists(query_script):
                logger.warning(f"[FINANCE] NeoData查询脚本不存在: {query_script}")
                return False
        
        return True
    
    def query_neodata(self, query: str, data_type: str = "all") -> Optional[Dict]:
        """查询NeoData金融数据"""
        if not self.neodata_enabled or "neodata" not in self.data_sources:
            logger.debug("[FINANCE] NeoData功能未启用或不在数据源列表中")
            return None
        
        # 生成缓存键（基于查询和数据类型）
        cache_key = f"{self.cache_prefix}neodata:{hash(query + data_type):016x}"
        
        # 检查缓存
        cached = global_cache.get(cache_key)
        if cached:
            logger.debug(f"[FINANCE] 从缓存获取NeoData数据: {query[:50]}...")
            return cached
        
        try:
            # 构建查询命令
            query_script = os.path.join(self.neodata_skill_path, "scripts", "query.py")
            cmd = [
                self.python_cmd, query_script,
                "--query", query,
                "--data-type", data_type
            ]
            
            logger.debug(f"[FINANCE] 执行NeoData查询: {' '.join(cmd)}")
            
            # 执行查询
            result = subprocess.run(
                cmd,
                cwd=self.neodata_skill_path,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                # 尝试解析JSON响应
                try:
                    data = json.loads(result.stdout)
                    
                    # 检查API响应状态
                    if data.get('code') == '200' and data.get('suc'):
                        # 缓存结果
                        global_cache.set(cache_key, data, ttl=config.FINANCE_CACHE_TTL)
                        logger.info(f"[FINANCE] NeoData查询成功: {query[:50]}...")
                        return data
                    else:
                        error_msg = data.get('msg', '未知错误')
                        logger.warning(f"[FINANCE] NeoData API错误: {error_msg}")
                        
                        # 如果是鉴权错误，尝试重新获取token
                        if data.get('code') in ['40101', '401'] or 'token' in error_msg.lower() or '认证' in error_msg:
                            logger.info("[FINANCE] 检测到鉴权错误，尝试重新获取token...")
                            self._refresh_neodata_token()
                            return None  # 返回None，调用方应该重试
                except json.JSONDecodeError as e:
                    logger.error(f"[FINANCE] JSON解析失败: {e}, 响应: {result.stdout[:200]}")
            else:
                logger.error(f"[FINANCE] NeoData执行失败: {result.stderr}")
                
        except Exception as e:
            logger.error(f"[FINANCE] NeoData查询异常: {e}")
        
        return None
    
    def _refresh_neodata_token(self) -> bool:
        """刷新NeoData token"""
        try:
            from connect_cloud_service import connect_cloud_service
            
            # 调用connect_cloud_service获取新token
            result = connect_cloud_service()
            if result and 'token' in result:
                token = result['token']
                
                # 保存token
                query_script = os.path.join(self.neodata_skill_path, "scripts", "query.py")
                cmd = [self.python_cmd, query_script, "--save-token", token]
                
                result = subprocess.run(
                    cmd,
                    cwd=self.neodata_skill_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                
                if result.returncode == 0:
                    logger.info("[FINANCE] NeoData token刷新成功")
                    return True
                else:
                    logger.error(f"[FINANCE] 保存token失败: {result.stderr}")
            else:
                logger.error("[FINANCE] 无法获取新的token")
                
        except Exception as e:
            logger.error(f"[FINANCE] 刷新token异常: {e}")
        
        return False
    
    def get_market_price(self, symbol: str, asset_type: str = "forex") -> Optional[Dict]:
        """获取市场价格数据"""
        if not self.is_available():
            return None
        
        # 根据资产类型生成查询
        if asset_type == "gold":
            query = f"{symbol}现货价格 最新行情"
        elif asset_type == "stock":
            query = f"{symbol}股价 最新行情"
        elif asset_type == "index":
            query = f"{symbol}指数 最新行情"
        else:  # forex
            query = f"{symbol}汇率 最新行情"
        
        result = self.query_neodata(query, data_type="api")
        if not result:
            return None
        
        # 解析价格数据
        try:
            api_data = result.get('data', {}).get('apiData', {})
            if api_data and api_data.get('apiRecall'):
                for recall in api_data['apiRecall']:
                    if '行情' in recall.get('type', '') or '价格' in recall.get('type', ''):
                        return {
                            'symbol': symbol,
                            'asset_type': asset_type,
                            'data_type': recall.get('type', ''),
                            'description': recall.get('desc', ''),
                            'content': recall.get('content', ''),
                            'raw_data': recall,
                            'timestamp': time.time(),
                            'source': 'neodata'
                        }
        except Exception as e:
            logger.error(f"[FINANCE] 解析价格数据失败: {e}")
        
        return None
    
    def get_forex_rate(self, pair: str = "USDCNY") -> Optional[Dict]:
        """获取外汇汇率"""
        return self.get_market_price(pair, "forex")
    
    def get_gold_price(self) -> Optional[Dict]:
        """获取黄金价格"""
        return self.get_market_price("黄金", "gold")
    
    def get_stock_price(self, symbol: str) -> Optional[Dict]:
        """获取股票价格"""
        return self.get_market_price(symbol, "stock")
    
    def get_financial_statements(self, symbol: str, statement_type: str = "income") -> Optional[Dict]:
        """获取财务报表"""
        if not self.is_available():
            return None
        
        query_map = {
            "income": f"{symbol}利润表 最新财报",
            "balance": f"{symbol}资产负债表 最新财报", 
            "cashflow": f"{symbol}现金流量表 最新财报",
            "all": f"{symbol}最新财务报表 财报"
        }
        
        query = query_map.get(statement_type, f"{symbol}财务报表")
        result = self.query_neodata(query, data_type="api")
        
        if result:
            return {
                'symbol': symbol,
                'statement_type': statement_type,
                'data': result.get('data', {}),
                'timestamp': time.time(),
                'source': 'neodata'
            }
        
        return None
    
    def get_macro_data(self, indicator: str) -> Optional[Dict]:
        """获取宏观经济数据"""
        if not self.is_available():
            return None
        
        query_map = {
            "gdp": "中国GDP数据 最新",
            "cpi": "中国CPI数据 最新",
            "ppi": "中国PPI数据 最新",
            "pmi": "中国PMI数据 最新",
            "interest_rate": "中国利率 最新",
            "shibor": "Shibor利率 最新"
        }
        
        query = query_map.get(indicator, f"{indicator}数据")
        result = self.query_neodata(query, data_type="api")
        
        if result:
            return {
                'indicator': indicator,
                'data': result.get('data', {}),
                'timestamp': time.time(),
                'source': 'neodata'
            }
        
        return None
    
    def get_market_sentiment(self) -> Optional[Dict]:
        """获取市场情绪数据"""
        if not self.is_available():
            return None
        
        # 查询市场情绪相关数据
        queries = [
            "A股市场情绪 今日",
            "北向资金流向 今日",
            "龙虎榜数据 最新",
            "板块资金流向 今日"
        ]
        
        results = {}
        for query in queries[:2]:  # 只查询前两个以提高性能
            result = self.query_neodata(query, data_type="api")
            if result:
                results[query] = result
        
        if results:
            return {
                'sentiment_data': results,
                'timestamp': time.time(),
                'source': 'neodata'
            }
        
        return None
    
    def get_enhanced_market_analysis(self, symbol: str, asset_type: str = "forex") -> Dict:
        """获取增强的市场分析（包含外部数据）"""
        analysis = {
            'symbol': symbol,
            'asset_type': asset_type,
            'timestamp': time.time(),
            'price_data': None,
            'macro_data': None,
            'sentiment_data': None,
            'external_data_available': False
        }
        
        if not self.is_available():
            return analysis
        
        # 并行获取多种数据（这里简化实现为顺序获取）
        price_data = self.get_market_price(symbol, asset_type)
        macro_data = self.get_macro_data("gdp")
        sentiment_data = self.get_market_sentiment()
        
        analysis.update({
            'price_data': price_data,
            'macro_data': macro_data,
            'sentiment_data': sentiment_data,
            'external_data_available': any([price_data, macro_data, sentiment_data])
        })
        
        return analysis
    
    def test_connection(self) -> Dict:
        """测试金融数据连接"""
        test_results = {
            'enabled': self.enabled,
            'neodata_enabled': self.neodata_enabled,
            'neodata_path_exists': os.path.exists(self.neodata_skill_path),
            'python_command': self.python_cmd,
            'connection_tests': {}
        }
        
        if self.is_available():
            # 测试基本查询
            try:
                # 测试黄金价格查询（通用资产）
                gold_price = self.get_gold_price()
                test_results['connection_tests']['gold_price'] = {
                    'success': gold_price is not None,
                    'has_data': bool(gold_price)
                }
                
                # 测试外汇查询
                usdcny_rate = self.get_forex_rate("USDCNY")
                test_results['connection_tests']['forex_rate'] = {
                    'success': usdcny_rate is not None,
                    'has_data': bool(usdcny_rate)
                }
                
                test_results['overall_status'] = '可用'
                
            except Exception as e:
                test_results['connection_tests']['error'] = str(e)
                test_results['overall_status'] = f'错误: {e}'
        else:
            test_results['overall_status'] = '不可用'
        
        return test_results


# 全局实例
_finance_data_integration: Optional[FinanceDataIntegration] = None

def get_finance_data_integration() -> FinanceDataIntegration:
    """获取金融数据集成实例（单例模式）"""
    global _finance_data_integration
    if _finance_data_integration is None:
        _finance_data_integration = FinanceDataIntegration()
    return _finance_data_integration


# 快捷函数
def get_forex_rate(pair: str = "USDCNY") -> Optional[Dict]:
    """快捷函数：获取外汇汇率"""
    finance = get_finance_data_integration()
    return finance.get_forex_rate(pair) if finance.is_available() else None

def get_gold_price() -> Optional[Dict]:
    """快捷函数：获取黄金价格"""
    finance = get_finance_data_integration()
    return finance.get_gold_price() if finance.is_available() else None

def get_market_sentiment() -> Optional[Dict]:
    """快捷函数：获取市场情绪"""
    finance = get_finance_data_integration()
    return finance.get_market_sentiment() if finance.is_available() else None

def get_enhanced_market_analysis(symbol: str, asset_type: str = "forex") -> Dict:
    """快捷函数：获取增强的市场分析"""
    finance = get_finance_data_integration()
    return finance.get_enhanced_market_analysis(symbol, asset_type)


if __name__ == "__main__":
    """模块测试"""
    print("金融数据集成模块测试")
    print("=" * 60)
    
    finance = get_finance_data_integration()
    
    # 测试连接
    print("测试金融数据连接...")
    test_results = finance.test_connection()
    
    print(f"金融数据集成可用: {test_results.get('overall_status', '未知')}")
    print(f"Python命令: {test_results.get('python_command')}")
    print(f"NeoData路径存在: {test_results.get('neodata_path_exists')}")
    
    # 显示测试结果
    for test_name, result in test_results.get('connection_tests', {}).items():
        print(f"  {test_name}: {'成功' if result.get('success') else '失败'}")
    
    if test_results.get('overall_status') == '可用':
        print("\n测试实际数据查询...")
        
        # 测试黄金价格
        print("查询黄金价格...")
        gold_price = finance.get_gold_price()
        if gold_price:
            print(f"  黄金价格查询成功")
            print(f"  数据来源: {gold_price.get('source')}")
            print(f"  数据类型: {gold_price.get('data_type')}")
        else:
            print("  黄金价格查询失败")
        
        # 测试外汇汇率
        print("\n查询USDCNY汇率...")
        forex_rate = finance.get_forex_rate("USDCNY")
        if forex_rate:
            print(f"  USDCNY汇率查询成功")
            print(f"  数据来源: {forex_rate.get('source')}")
        else:
            print("  USDCNY汇率查询失败")
    
    print("\n测试完成")