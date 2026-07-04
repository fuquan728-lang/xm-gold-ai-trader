# MQL5 Experts 当前清单

最后更新：2026-07-01

`MQL5/Experts/` 现在只保留当前主线需要的 EA。旧版、实验版、诊断工具和网格策略已归档到 `archive/cleanup_20260701/mql5_legacy_experts/`，不要再作为日常入口使用。

## 当前保留

| EA | 状态 | 说明 |
|----|------|------|
| `AI_Trader_V3.2_Integrated.mq5` | 主交易 EA | 当前唯一自动交易入口。默认 `InpAllowLiveTrading=false`、`InpRequireDemoAccount=true`。SL/TP 输入按 pips 处理。 |
| `XM_Gold_AI_Trader_SafetyGuard.mq5` | 只读安全监控 | 不下单，用于图表侧安全观察。 |

## 已归档

以下文件不再放在 `MQL5/Experts/` 根目录：

- `AI_Trader_Integrated*`
- `AI_Trader_V2.1_Safe`
- `GridTrader_GOLD`
- `FindPath`
- `MQL5_Update`
- `MQL5_FileUpdate`
- `socket_test`

## 使用规则

1. 同一图表不要加载多个 AI Trader 版本。
2. 新安装只编译并加载 `AI_Trader_V3.2_Integrated` 或 `XM_Gold_AI_Trader_SafetyGuard`。
3. 需要回看旧代码时，只读归档目录，不要把旧 EA 复制回主目录。
4. 新实验另建分支或放入 `archive/`，不要污染当前主线。
