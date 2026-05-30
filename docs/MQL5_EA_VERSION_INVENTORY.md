# MQL5 Experts EA 版本清单

**最后更新**: 2026-05-30 (v0.5.8)  
**目的**: 记录所有 `MQL5/Experts/` 中的 EA 版本，标注状态，防止同时加载多个版本。

## 当前推荐/活跃 EA

| EA | 版本 | 状态 | 说明 |
|----|------|------|------|
| `AI_Trader_V3.2_Integrated` | v3.20 | **活跃** | 当前主版本。集成账户数据推送、动态止损止盈、多时间框架、风险检查 |
| `AI_Trader_Integrated` | v3.10 | **活跃备用** | 上一主版本。与 V3.2 大部分兼容 |
| `XM_Gold_AI_Trader_SafetyGuard` | — | **活跃** | 独立安全监控 EA，只读不交易 |
| `TradeCommandEA` | v2.3 | **活跃** | 交易命令执行 EA，读取 trade_command.txt |
| `GOLD_Short_EA` | — | **活跃** | 独立黄金做空策略 |
| `Advanced_GOLD_EA` | — | **活跃** | 独立高级黄金策略 |

## Legacy EA（历史版本，非当前推荐）

| EA | 版本 | 状态 | 说明 |
|----|------|------|------|
| `AI_Trader_V2.1_Safe` | v3.11 | **Legacy** | V2.1 安全修复版，已被 V3.2 完全替代。仍可编译但非推荐 |
| `AI_Trader_Integrated_Optimized` | v3.10 | **Legacy** | V3.0 性能优化版，已被 V3.2 替代 |
| `AI_Trader_Integrated_Socket` | v5.00 | **Legacy/Archive** | Socket 通信版。Socket 模式已废弃，File 兼容部分仍有参考价值 |

## 辅助/工具 EA

| EA | 说明 | 状态 |
|----|------|------|
| `socket_test` | Socket 连接诊断工具 | **工具** |
| `MQL5_Update` | MT5 → Python 数据推送模块 | **工具** |
| `MQL5_FileUpdate` | File 模式数据更新 | **Legacy 工具** — 功能可能已整合到 MQL5_Update |
| `GridTrader_GOLD` | 独立网格交易策略 | **活跃** |
| `FindPath` | MT5 路径查找工具 | **活跃** |
| `TradeCommand` | MT5 基础 trade command EA | **工具** |
| `XAUUSD_AI_Trader` | 旧版黄金 AI 交易 EA | **Legacy** |

## 编译状态

| EA | 已编译 .ex5 | 最后编译 |
|----|-------------|----------|
| `AI_Trader_V3.2_Integrated` | ✅ 81,152 bytes | 2026-05-29 |
| `AI_Trader_Integrated` | ✅ 98,672 bytes | 2026-05-29 |
| `AI_Trader_V2.1_Safe` | ✅ 83,012 bytes | 2026-05-29 |
| `AI_Trader_Integrated_Optimized` | ✅ | — |
| `AI_Trader_Integrated_Socket` | ✅ | — |
| `safety_test` | ✅ | 2026-05-29 |

## ⚠️ 注意事项

1. **不要同时加载多个 AI_Trader 版本**到同一 MT5 图表 — 会导致重复交易和 Magic Number 冲突。
2. **Legacy EA 保留编译**但不应作为主交易 EA 使用。
3. **V3.2 是当前推荐版本**，包含最新的风控检查、保证金检查、动态止损止盈、Magic Number 验证。

## Archive 候选（下次清理）

以下 EA 可在下一轮清理中移至 `MQL5/Experts/archive/`：
- `AI_Trader_V2.1_Safe.mq5` + `.ex5`
- `AI_Trader_Integrated_Optimized.mq5` + `.ex5`
- `AI_Trader_Integrated_Socket.mq5` + `.ex5`
- `XAUUSD_AI_Trader.mq5` + `.ex5`

**当前不删除** — 保留编译和文件，仅标记状态。
