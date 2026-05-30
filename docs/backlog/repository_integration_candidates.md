# 仓库整合候选清单

**创建时间**: 2026-05-30 (v0.5.8)  
**状态**: BACKLOG — 等待未来 review 和决策，当前不做任何代码合并。

## 1. 双架构风险管理系统

| 文件 | 位置 | 大小 |
|------|------|------|
| 旧版 | `core/risk_manager.py` | 49KB |
| 新版 | `src/strategy/risk_manager.py` | 15KB |

**风险**: 两套完全不同的风控实现共存。旧版是 V4.0 单例模式，新版是 V0.5+ 不可变 dataclass。需要确认：
- 两个版本不会同时被调用
- 生产路径使用的是哪个版本
- 迁移方案：逐步将旧版功能迁移到新版设计模式

**暂不合并原因**: 需要先确认生产路径无冲突，再做代码级整合。

## 2. 双架构交易执行引擎

| 文件 | 位置 | 大小 |
|------|------|------|
| 旧版 | `core/trade_executor.py` | 30KB |
| 新版 | `src/broker/order_executor.py` | 11KB |

**风险**: 旧版支持多平台（MT5/OANDA/IBKR/Alpaca），新版专注 MT5。需要确认：
- 多平台支持是否还需要
- 新版是否可补齐必要功能后切换

**暂不合并原因**: 功能差距大，需评估需求后再整合。

## 3. WebSocket 处理器兼容垫片

| 文件 | 大小 | 说明 |
|------|------|------|
| `core/websocket_handler.py` | 0.6KB | 仅 17 行，是 `websocket_handler_enhanced` 的别名导入 |
| `core/websocket_handler_enhanced.py` | 23KB | 实际实现 |

**方案**: 将所有 `from core.websocket_handler import ...` 改为 `from core.websocket_handler_enhanced import ...`，然后删除垫片文件。

**暂不合并原因**: 需要先确认所有引用点。

## 4. 金融数据模块重叠

| 文件 | 大小 | 功能 |
|------|------|------|
| `core/finance_data_integration.py` | 18KB | NeoData 自然语言金融搜索 |
| `core/financial_data_enhancer.py` | 39KB | aiohttp 外部金融数据集成 |

**风险**: 两个模块都做外部金融数据集成，功能有重叠。需要：
- 明确分工或合并
- 确定哪个是主数据路径

**暂不合并原因**: 需要了解使用场景后决策。

## 5. MQL5 数据推送模块

| 文件 | 说明 |
|------|------|
| `MQL5/Experts/MQL5_Update.mq5` | 当前数据推送模块 (v3.1) |
| `MQL5/Experts/MQL5_FileUpdate.mq5` | File 模式专用数据更新 |

**问题**: MQL5_FileUpdate 功能可能已整合到 MQL5_Update，需确认是否可以删除。

**暂不合并原因**: 需要确认 MQL5_Update 确实覆盖了 MQL5_FileUpdate 的所有场景。

## 6. 可迁移测试

| 文件 | 当前位置 | 建议目标 |
|------|----------|----------|
| `test_deepseek_config.py` | `legacy_v4/tests/` | `tests/` |
| `test_mql5_account_data.py` | `legacy_v4/tests/` | `tests/` |
| `test_risk_gate.py` | `legacy_v4/tests/` | `tests/` |

**说明**: 这三个测试使用当前仍存在的模块，可以迁移到主测试目录。

**暂不迁移原因**: 需先确保测试在隔离环境中仍然通过。

---

## 决策时间线

| 里程碑 | 条件 | 行动 |
|--------|------|------|
| v0.5.8 完成 | 本文件创建 | 仅记录，不做合并 |
| 后续 review | 团队讨论 | 逐项决策：合并/删除/保留 |
| 下次 cleanup | 有新检查点 | 执行已决策的整合操作 |
