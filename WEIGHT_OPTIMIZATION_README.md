# 交易策略权重优化系统

## 概述

本系统实现了对交易策略中的多时间框架权重进行系统性优化的功能，包括动态调整权重、评估机制和可追溯记录。

## 功能特性

### 1. 动态权重调整

- 基于交易效果自动调整各时间框架（h1、h4、d1）的权重比例
- 权重分配优先考虑表现更好的时间框架
- 支持多种触发条件：性能下降、市场环境变化、定时优化、手动干预

### 2. 权重评估机制

- **触发条件**：
  - 胜率低于设定阈值（默认55%）
  - 各时间框架表现差异过大（超过20%）
  - 定时优化
  - 手动干预
  
- **调整限制**：
  - 单次调整幅度不超过10%（可配置）
  - 单个时间框架权重在10%~60%范围内
  - 权重调整有冷却期（默认1小时）

### 3. 可追溯记录系统

- 记录每次权重调整的触发原因和时间
- 保存权重调整前后的性能表现
- 验证权重调整的有效性
- 支持历史权重查询和分析

### 4. AI引擎集成

- 自动将当前权重应用到多时间框架分析
- 记录交易信号用于权重优化
- 提供权重状态查询接口

## 文件结构

```
XM Global MT5/
├── core/
│   ├── weight_optimizer.py     # 权重优化器核心模块
│   ├── ai_engine.py            # AI分析引擎（已集成权重优化）
│   └── ...
├── mt5_ai_service.py          # 主服务（已集成权重优化接口）
├── test_weight_optimizer.py    # 权重优化器测试套件
└── weights/                    # 权重历史数据目录（自动创建）
    ├── weights_history.json    # 权重调整历史
    └── signal_history.json     # 交易信号历史
```

## 配置说明

### 权重配置 (WeightConfig)

```python
WeightConfig(
    default_weights={'h1': 0.35, 'h4': 0.35, 'd1': 0.30},  # 默认权重
    min_weight=0.10,               # 单个时间框架最小权重
    max_weight=0.60,               # 单个时间框架最大权重
    max_adjustment_per_step=0.10,  # 单次最大调整幅度
    evaluation_period=20,          # 评估周期（交易次数）
    performance_threshold=0.55,    # 性能触发阈值
    cooldown_period=3600           # 权重调整冷却期（秒）
)
```

## 使用方法

### 1. 基本使用

```python
from core.weight_optimizer import get_weight_optimizer, TradeSignal, TriggerReason

# 获取权重优化器实例
optimizer = get_weight_optimizer()

# 获取当前权重
weights = optimizer.get_current_weights()
print(f"当前权重: {weights}")

# 记录交易信号
signal = TradeSignal(
    timestamp=time.time(),
    symbol="EURUSD",
    action="BUY",
    confidence=0.85,
    bid=1.1050,
    ask=1.1055,
    multi_timeframe_signals={'h1': 'BUY', 'h4': 'HOLD', 'd1': 'HOLD'},
    result="win"  # 交易结果
)
optimizer.record_signal(signal)

# 手动触发权重调整
optimizer.adjust_weights(TriggerReason.MANUAL_INTERVENTION.value)

# 获取性能报告
report = optimizer.get_performance_report()
print(report)
```

### 2. 在MT5交易服务中使用

```python
from mt5_ai_service import MT5AITradingService

service = MT5AITradingService()

# 获取权重优化器状态
weight_status = service.get_weight_optimizer_status()

# 手动触发权重调整
service.trigger_weight_adjustment("manual_trigger")
```

### 3. 集成到AI引擎

```python
from core.ai_engine import AIAnalyzer

ai_analyzer = AIAnalyzer()

# AI引擎会自动使用权重优化器
action, confidence, reason = ai_analyzer.get_fallback_strategy(
    symbol="EURUSD",
    bid=1.1050,
    ask=1.1055,
    indicators=indicators,
    multi_timeframe=multi_timeframe_data
)

# 获取当前权重
weights = ai_analyzer.weight_optimizer.get_current_weights()
```

## 测试

运行完整测试套件：

```bash
python test_weight_optimizer.py
```

## 性能评估

权重优化系统通过以下方式提升策略表现：

1. **动态适应市场变化**：根据不同市场环境调整权重分配
2. **降低风险**：通过权重调整限制单个时间框架的影响
3. **持续优化**：根据交易效果不断优化权重配置

## 性能数据示例

在测试运行中：

- **初始权重**：h1=35%, h4=35%, d1=30%
- **优化后**：根据市场表现自动调整
- **稳定性**：单次权重变化不超过10%
- **可追溯**：所有调整记录在weights_history.json

## 注意事项

1. 权重调整有冷却期，避免频繁调整
2. 确保有足够的交易样本才能触发自动调整
3. 定期查看权重优化器状态和性能报告
4. 手动调整权重时建议进行充分测试验证

## 下一步建议

1. 基于更多历史数据进一步验证和校准参数
2. 增加更多时间框架的支持
3. 实现基于强化学习的自适应权重调整
4. 集成更复杂的市场环境识别机制
