# MT5 AI交易系统 - 金融数据集成方案

## 执行摘要

基于"执行下一步"指令和长期记忆中的"未来优化方向"，本方案实现金融数据检索技能集成，增强系统市场分析能力。

## 当前状态分析

### 已完成的核心组件
1. ✅ 组件协调性验证完成 (2026-04-23)
2. ✅ 异步优化架构集成 (`async-python-patterns`技能)
3. ✅ MQL5实时数据集成
4. ✅ 风险管理与AI引擎协调
5. ✅ Windows环境适配 (编码问题修复)

### 可用的金融数据技能
1. **neodata-financial-search** - 自然语言通用金融数据搜索
   - 覆盖股票(A股/港股/美股)、指数、板块、基金、宏观经济、外汇、大宗商品
   - 支持行情报价、财务报表、资金流向、研报评级、事件公告
   - 即问即答，实时数据

2. **finance-data-retrieval** - 结构化API金融数据检索
   - 209个API接口，15个数据类别
   - 精确的结构化数据查询
   - 补充neodata的数据覆盖

## 集成目标

### 阶段1: 配置与基础设施 (立即实施)
1. 扩展配置系统支持金融数据功能
2. 创建金融数据集成核心模块
3. 建立数据缓存和更新机制

### 阶段2: 市场数据分析器增强 (1-2天)
1. 集成NeoData作为外部数据源
2. 扩展MarketDataAnalyzer支持实时金融数据
3. 添加宏观经济数据支持

### 阶段3: AI引擎优化 (2-3天)
1. 在AI提示词中集成实时市场数据
2. 增强多维度分析能力
3. 添加基本面分析支持

### 阶段4: 风险管理增强 (1-2天)
1. 基于实时市场数据的风险评估
2. 市场波动率监控
3. 相关性分析和风险分散

## 详细实施方案

### 1. 配置系统扩展

**文件**: `core/config.py`

```python
# 金融数据集成配置
FINANCE_DATA_ENABLED = os.getenv("FINANCE_DATA_ENABLED", "false").lower() == "true"
NEODATA_ENABLED = os.getenv("NEODATA_ENABLED", "true").lower() == "true"
EXTERNAL_DATA_SOURCES = os.getenv("EXTERNAL_DATA_SOURCES", "neodata,yahoo").split(",")
MAX_EXTERNAL_RETRIES = int(os.getenv("MAX_EXTERNAL_RETRIES", "3"))
NEODATA_TOKEN_PATH = os.path.expanduser("~/.workbuddy/.neodata_token")

# 数据缓存配置
FINANCE_CACHE_TTL = int(os.getenv("FINANCE_CACHE_TTL", "300"))  # 5分钟
MARKET_DATA_UPDATE_INTERVAL = int(os.getenv("MARKET_DATA_UPDATE_INTERVAL", "60"))  # 60秒
```

### 2. 创建金融数据集成模块

**文件**: `core/finance_data_integration.py`

```python
"""
金融数据集成模块 - 统一管理外部金融数据源
"""

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import subprocess

from core.config import config
from core.logger import logger
from core.cache import global_cache


class FinanceDataIntegration:
    """金融数据集成管理器"""
    
    def __init__(self):
        self.enabled = config.FINANCE_DATA_ENABLED
        self.neodata_enabled = config.NEODATA_ENABLED
        self.data_sources = config.EXTERNAL_DATA_SOURCES
        self.max_retries = config.MAX_EXTERNAL_RETRIES
        
        # NeoData技能路径
        self.neodata_skill_path = r"C:\Users\彩印\.workbuddy\plugins\marketplaces\cb_teams_marketplace\plugins\finance-data\skills\neodata-financial-search"
        
        # 缓存键前缀
        self.cache_prefix = "finance_data:"
        
        logger.info(f"[FINANCE] 金融数据集成初始化: enabled={self.enabled}, sources={self.data_sources}")
    
    def query_neodata(self, query: str, data_type: str = "all") -> Optional[Dict]:
        """查询NeoData金融数据"""
        if not self.neodata_enabled:
            logger.warning("[FINANCE] NeoData功能未启用")
            return None
        
        cache_key = f"{self.cache_prefix}neodata:{query}:{data_type}"
        
        # 检查缓存
        cached = global_cache.get(cache_key)
        if cached:
            logger.debug(f"[FINANCE] 从缓存获取NeoData数据: {query}")
            return cached
        
        try:
            # 构建命令
            cmd = [
                "python", "scripts/query.py",
                "--query", query,
                "--data-type", data_type
            ]
            
            # 执行查询
            result = subprocess.run(
                cmd,
                cwd=self.neodata_skill_path,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data.get('code') == '200' and data.get('suc'):
                    # 缓存结果
                    global_cache.set(cache_key, data, ttl=config.FINANCE_CACHE_TTL)
                    logger.info(f"[FINANCE] NeoData查询成功: {query}")
                    return data
                else:
                    logger.warning(f"[FINANCE] NeoData API错误: {data.get('msg')}")
            else:
                logger.error(f"[FINANCE] NeoData执行失败: {result.stderr}")
                
        except Exception as e:
            logger.error(f"[FINANCE] NeoData查询异常: {e}")
        
        return None
    
    def get_market_price(self, symbol: str, asset_type: str = "forex") -> Optional[Dict]:
        """获取市场价格数据"""
        query = f"{symbol}最新行情"
        
        if asset_type == "gold":
            query = f"{symbol}现货价格"
        elif asset_type == "stock":
            query = f"{symbol}股价"
        elif asset_type == "index":
            query = f"{symbol}指数"
        
        result = self.query_neodata(query)
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
                            'data': recall.get('content', ''),
                            'type': recall.get('type', ''),
                            'timestamp': time.time()
                        }
        except Exception as e:
            logger.error(f"[FINANCE] 解析价格数据失败: {e}")
        
        return None
    
    def get_financial_statements(self, symbol: str, statement_type: str = "income") -> Optional[Dict]:
        """获取财务报表"""
        query_map = {
            "income": f"{symbol}利润表",
            "balance": f"{symbol}资产负债表", 
            "cashflow": f"{symbol}现金流量表",
            "all": f"{symbol}最新财报"
        }
        
        query = query_map.get(statement_type, f"{symbol}财务报表")
        return self.query_neodata(query)
    
    def get_macro_data(self, indicator: str) -> Optional[Dict]:
        """获取宏观经济数据"""
        query_map = {
            "gdp": "中国GDP数据",
            "cpi": "中国CPI数据",
            "ppi": "中国PPI数据",
            "pmi": "中国PMI数据",
            "interest_rate": "中国利率",
            "shibor": "Shibor利率"
        }
        
        query = query_map.get(indicator, f"{indicator}数据")
        return self.query_neodata(query)
    
    def get_market_sentiment(self) -> Optional[Dict]:
        """获取市场情绪数据"""
        queries = [
            "A股市场情绪",
            "北向资金流向",
            "龙虎榜数据",
            "板块资金流向"
        ]
        
        results = {}
        for query in queries[:2]:  # 只查询前两个
            result = self.query_neodata(query)
            if result:
                results[query] = result
        
        return results if results else None


# 全局实例
_finance_data_integration: Optional[FinanceDataIntegration] = None

def get_finance_data_integration() -> FinanceDataIntegration:
    """获取金融数据集成实例"""
    global _finance_data_integration
    if not _finance_data_integration:
        _finance_data_integration = FinanceDataIntegration()
    return _finance_data_integration
```

### 3. 扩展市场数据分析器

**文件**: `core/market_data_analyzer.py` (扩展)

```python
# 在MarketDataAnalyzer类中添加方法

def add_external_market_data(self, symbol: str, asset_type: str = "forex"):
    """添加外部市场数据"""
    if not config.FINANCE_DATA_ENABLED:
        return
    
    from core.finance_data_integration import get_finance_data_integration
    
    finance = get_finance_data_integration()
    price_data = finance.get_market_price(symbol, asset_type)
    
    if price_data:
        # 转换格式并添加到分析器
        market_data = {
            "type": "external_price",
            "symbol": symbol,
            "asset_type": asset_type,
            "timestamp": time.time(),
            "data": price_data,
            "source": "neodata"
        }
        
        self.add_market_data(market_data)
        logger.info(f"[MARKET] 添加外部市场数据: {symbol} ({asset_type})")

def get_enhanced_market_analysis(self, symbol: str, timeframe: str) -> Dict:
    """获取增强的市场分析（包含外部数据）"""
    base_analysis = self.get_market_analysis(symbol, timeframe)
    
    if config.FINANCE_DATA_ENABLED:
        from core.finance_data_integration import get_finance_data_integration
        
        finance = get_finance_data_integration()
        
        # 获取相关市场数据
        related_data = {
            "macro": finance.get_macro_data("gdp"),
            "sentiment": finance.get_market_sentiment()
        }
        
        base_analysis["external_data"] = {
            "available": True,
            "related_data": {k: v is not None for k, v in related_data.items()},
            "timestamp": time.time()
        }
    
    return base_analysis
```

### 4. 增强AI引擎

**文件**: `core/ai_engine.py` (扩展)

```python
# 在AIAnalyzer类的build_prompt方法中添加

# 在构建提示词的部分添加外部市场数据
if include_account_context and config.FINANCE_DATA_ENABLED:
    from core.finance_data_integration import get_finance_data_integration
    
    finance = get_finance_data_integration()
    
    # 获取相关市场数据
    market_price = finance.get_market_price(symbol, "forex")
    macro_data = finance.get_macro_data("gdp")
    
    if market_price:
        prompt_sections.append(f"\n【外部市场数据】")
        prompt_sections.append(f"- 实时行情: {market_price.get('type', 'N/A')}")
        # 解析并添加具体数据...
    
    if macro_data:
        prompt_sections.append(f"\n【宏观经济环境】")
        prompt_sections.append(f"- GDP数据: 已获取最新宏观经济指标")
        # 解析并添加具体数据...

# 在AIAnalyzer类中添加新方法
def analyze_with_external_data(self, symbol: str, bid: float, ask: float, 
                              current_time: float, include_finance_data: bool = True) -> Dict:
    """使用外部金融数据进行增强分析"""
    # 基础分析
    analysis = self.analyze(symbol, bid, ask, current_time)
    
    if include_finance_data and config.FINANCE_DATA_ENABLED:
        from core.finance_data_integration import get_finance_data_integration
        
        finance = get_finance_data_integration()
        
        # 获取外部数据
        external_data = {
            "market_price": finance.get_market_price(symbol),
            "macro": finance.get_macro_data("gdp"),
            "sentiment": finance.get_market_sentiment()
        }
        
        analysis["external_data"] = {
            "available": True,
            "data_sources": [k for k, v in external_data.items() if v],
            "timestamp": current_time
        }
    
    return analysis
```

### 5. 测试与验证

**文件**: `tests/test_finance_integration.py`

```python
"""
金融数据集成测试
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.finance_data_integration import get_finance_data_integration
from core.market_data_analyzer import get_market_data_analyzer
from core.ai_engine import AIAnalyzer


def test_finance_integration_module():
    """测试金融数据集成模块"""
    print("测试金融数据集成模块...")
    
    finance = get_finance_data_integration()
    assert finance is not None
    print("✅ 金融数据集成模块初始化成功")
    
    # 测试配置
    assert hasattr(finance, 'enabled')
    print("✅ 配置检查通过")
    
    return True


def test_market_data_enhancement():
    """测试市场数据增强"""
    print("\n测试市场数据增强...")
    
    analyzer = get_market_data_analyzer()
    
    # 测试添加模拟数据
    test_data = {
        "type": "price",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "timestamp": time.time(),
        "open": 1.0850,
        "high": 1.0860,
        "low": 1.0840,
        "close": 1.0855,
        "volume": 1000,
        "source": "test"
    }
    
    analyzer.add_market_data(test_data)
    print("✅ 市场数据分析器增强测试通过")
    
    return True


def main():
    """主测试函数"""
    print("=" * 70)
    print("金融数据集成测试")
    print("=" * 70)
    
    tests = [
        test_finance_integration_module,
        test_market_data_enhancement
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            results.append(False)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("✅ 所有测试通过，金融数据集成准备就绪")
    else:
        print("⚠️  部分测试失败，需要检查配置")
    
    return passed == total


if __name__ == "__main__":
    import time
    success = main()
    sys.exit(0 if success else 1)
```

## 实施时间表

### 第1天: 基础框架
- [ ] 创建 `core/finance_data_integration.py`
- [ ] 扩展 `core/config.py` 添加金融数据配置
- [ ] 创建基础测试脚本
- [ ] 验证NeoData技能连接性

### 第2天: 核心集成
- [ ] 扩展 `core/market_data_analyzer.py`
- [ ] 实现数据缓存和更新机制
- [ ] 创建数据解析工具函数
- [ ] 测试端到端数据流

### 第3天: AI引擎增强
- [ ] 扩展 `core/ai_engine.py`
- [ ] 在AI提示词中集成外部数据
- [ ] 优化数据格式和显示
- [ ] 性能测试和优化

### 第4天: 系统集成与测试
- [ ] 集成到主服务 `mt5_ai_service_optimized.py`
- [ ] 创建HTTP仪表板面板
- [ ] 完整系统测试
- [ ] 文档编写

## 预期收益

### 1. 分析能力提升
- **实时市场数据**: 获取最新行情、财报、宏观经济指标
- **多维度分析**: 结合技术分析和基本面分析
- **市场情绪**: 集成资金流向、龙虎榜等情绪指标

### 2. 决策质量改善
- **更准确的趋势判断**: 基于更全面的市场信息
- **风险识别增强**: 考虑宏观经济和市场情绪因素
- **机会发现**: 基于数据驱动的机会识别

### 3. 系统价值提升
- **差异化竞争力**: 集成AI与实时金融数据的独特优势
- **用户信任度**: 基于真实市场数据的决策支持
- **扩展性**: 为未来更多数据源集成奠定基础

## 风险评估与缓解

### 风险1: 外部API稳定性
- **影响**: 数据获取失败影响分析质量
- **缓解**: 
  - 实现缓存机制，降低API依赖
  - 多个数据源备选
  - 优雅降级，API失败时使用现有数据

### 风险2: 性能影响
- **影响**: 外部API调用增加系统延迟
- **缓解**:
  - 异步数据获取
  - 合理的缓存策略
  - 后台更新，不影响实时决策

### 风险3: 数据一致性
- **影响**: 不同数据源数据口径不一致
- **缓解**:
  - 数据标准化处理
  - 来源标记和验证
  - 用户可选择数据源优先级

## 成功标准

### 技术成功标准
1. ✅ 金融数据集成模块可稳定运行
2. ✅ 数据缓存和更新机制有效
3. ✅ AI提示词正确集成外部数据
4. ✅ 系统性能影响在可接受范围(<10%延迟增加)

### 业务成功标准
1. ✅ 交易决策包含实时市场数据
2. ✅ 风险分析考虑宏观经济因素
3. ✅ 用户可通过仪表板查看市场数据
4. ✅ 系统分析报告更加全面和可信

## 下一步行动

### 立即行动 (今天)
1. **创建核心模块**: `core/finance_data_integration.py`
2. **扩展配置**: 在`core/config.py`中添加金融数据配置
3. **验证连接**: 测试NeoData技能可连接性

### 短期行动 (1-2天)
1. **集成市场数据分析器**
2. **实现数据缓存机制**
3. **创建基本测试用例**

### 中期行动 (3-5天)
1. **增强AI引擎**
2. **集成到主服务**
3. **性能优化和测试**

## 结论

金融数据集成是MT5 AI交易系统的重要演进方向，将显著提升系统的市场分析能力和决策质量。基于现有的组件协调性基础，实施本方案的技术风险可控，预期收益显著。

**建议立即开始实施阶段1，创建基础框架并验证技术可行性。**

---
**方案制定**: AI Assistant  
**制定时间**: 2026-04-23 09:40  
**预计工期**: 4-5天  
**优先级**: 高 (基于长期记忆中的优化方向)