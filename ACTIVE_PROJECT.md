# 当前唯一项目主线

本仓库现在只维护这一套运行入口。旧版 EA、实验脚本、一次性报告、临时测试和历史权重已经移入 `archive/cleanup_20260701/`，以后不要再放回根目录或 `MQL5/Experts/` 作为日常入口。

## 固定入口

- Python 服务：`mt5_ai_service.py`
- 启动脚本：`launch_ai_service.bat`
- 推荐启动命令：`python mt5_ai_service.py --mode file`
- Web Dashboard：`http://127.0.0.1:8000`

## MT5 只保留两个 EA

- 主交易 EA：`MQL5/Experts/AI_Trader_V3.2_Integrated.mq5`
- 只读安全监控：`MQL5/Experts/XM_Gold_AI_Trader_SafetyGuard.mq5`

不要再使用旧版 `AI_Trader_Integrated*`、`AI_Trader_V2.1_Safe`、`GridTrader_GOLD`、`socket_test` 等文件；它们只在归档中保留用于追溯。

## 当前安全模式

- DeepSeek 可用时正常分析。
- `ALLOW_FALLBACK_TRADING=false`，DeepSeek 不可用时只返回 HOLD。
- `MIN_INDICATOR_SIGNALS=3`，低质量或指标不一致的 BUY/SELL 降级为 HOLD。
- `MAX_TRADE_SPREAD_PIPS=3.0`，点差过大时降级为 HOLD。
- `.env` 不保存真实 API Key；真实 Key 通过系统环境变量注入。
- 如果系统环境变量没有有效 Key，服务会把 DeepSeek 视为不可用，并因后备交易关闭而返回 HOLD。
- 安全模式不复用缓存 BUY/SELL；交易信号必须重新通过 DeepSeek、指标校验和风险检查。
- EA 默认拦截同品种手动/其他 EA 持仓，避免重复或冲突开仓。
- EA 响应等待默认 45 秒，给 DeepSeek 正常分析留出时间。
- 文件通信必须带 `request_id`；EA 会丢弃 request_id 不匹配的旧响应。
- Python 响应和 ready 文件使用 tmp + atomic replace 写入，避免半截 JSON。
- EA 只有读到 `service_ready.json` 且 `ready=true` 时才发送交易请求。
- RL 模型默认禁用：`ENABLE_RL_MODEL=false`，当前阶段只用 DeepSeek + 本地规则/风控。

## 文件纪律

- 新实验、旧版本、一次性诊断结果放到 `archive/` 或单独分支，不放根目录。
- `MQL5/Experts/` 只放当前两个 EA。
- 运行产生的日志、数据库、请求响应 JSON、缓存文件不进入项目主线。
- 新增测试必须服务当前主线；不兼容旧 API 的测试放入归档或重写。
 
## v0.25.8 M5 Formal Observation Campaign

- Communication protocol is frozen at v0.25.7.
- Do not change request_id, stale response guard, ready gate, or atomic file write behavior during observation.
- Observation journal is enabled by default: `OBSERVATION_JOURNAL_ENABLED=true`.
- Observation JSONL path: `logs/m5_observations/YYYYMMDD.jsonl`.
- Checkpoint A target: 30 matched GOLD_ M5 observations.
- Checkpoint report command: `python scripts/m5_observation_report.py --target 30`.
- Pass condition: `matched_responses == total_requests`, `stale_responses_ignored == 0`, `timeouts == 0`, `trades_executed == 0`, and no malformed/missing required fields.
- Do not lower spread or confidence thresholds to force trades.

## v0.26.0 Spread Regime Study

- Profit readiness is blocked until spread cost is proven tradable.
- Analysis command: `python scripts/spread_regime_report.py --target 300`.
- Historical weekend command: `python scripts/spread_regime_report.py --historical-csv data/gold_m15.csv --symbol-info data/gold_m15.csv.symbol_info.json --target 300`.
- Alternative account/symbol/timeframe matrix: `python scripts/spread_tradeability_matrix.py --csv data/gold_m15.csv --csv data/eurusd_m15.csv --csv data/gbpusd_m15.csv --timeframes M15,H1,H4 --min-bars 100`.
- Lower-spread account scenario example: `python scripts/spread_tradeability_matrix.py --csv data/gold_m15.csv --timeframes M15,H1,H4 --min-bars 100 --assume-spread-pips GOLD_=2.5`.
- No-spread signal-quality check: `python scripts/signal_quality_without_spread_report.py --target 100`.
- Current study is read-only and uses `logs/m5_observations/*.jsonl`.
- Historical CSV mode is read-only and converts MT5 spread points to GOLD pips using symbol metadata.
- Tradeability matrix is read-only; zero-spread CSV data is treated as missing real spread evidence, not as a low-spread pass.
- Longer-timeframe candidates are research hypotheses only; they do not unlock live trading or threshold changes.
- If spread is ignored for research, keep confidence and non-spread quality gates active; do not treat raw BUY/SELL as tradable by itself.

## v0.26.2 Four-Pack Strategy Hypothesis Lab

- No-spread historical research command: `python scripts/strategy_four_pack_report.py --input data/gold_m15.csv --min-trades 10`.
- The report prints current support/resistance snapshots from the selected historical input, including research-only trigger, stop, take-profit, and invalidation levels.
- The report also includes reference level sources, nearest support/resistance, confirmation checklists, confluence scores, 1R partial exits, breakeven levels, trailing-start levels, and time-stop bars.
- Covered strategy families:
  - H1/H4 EMA50/EMA200 trend-following pullback.
  - London/New York breakout with rolling range and ATR expansion filter.
  - H1 trend + M15 RSI/MACD pullback continuation.
  - Low-volatility mean reversion near support/resistance, disabled in strong EMA trend.
- This report is R-multiple based and ignores spread/commission by design for hypothesis discovery only.
- Support/resistance levels in this report are historical-input snapshots unless the input is refreshed from MT5.
- Historical sample trades include setup card fields: level source, entry trigger, support/resistance, stop, 1R management, final target, invalidation, max hold bars, and confluence notes.
- Passing no-spread research is not permission to trade; any candidate must later pass spread/slippage stress, walk-forward, and demo-forward evidence.
- Production EA, v0.25.7 communication protocol, fallback trading, confidence threshold, and risk gates remain frozen.
- Keep protocol frozen at v0.25.7.
- Keep `ALLOW_FALLBACK_TRADING=false`, `ENABLE_RL_MODEL=false`, `MIN_CONFIDENCE=0.65`, and `MAX_TRADE_SPREAD_PIPS=3.0`.
- Do not tune prompt, confidence, spread threshold, or trade execution while the study is in progress.
- Initial baseline: no observed `spread_pips <= 3.0` window; all current BUY/SELL raw candidates are final HOLD.
- Pass direction: collect at least 300 GOLD_ M5 observations, then evaluate overall and session spread p50/p75.

## v0.26.3 Engineering Reliability Cleanup

- Scope: reliability cleanup only; no strategy tuning and no trade enablement.
- EA stale-response behavior: if `response_request_id != current_request_id`, log `STALE_RESPONSE_IGNORED`, keep `STATE_WAITING_RESPONSE`, and continue waiting for the current request until timeout.
- EA pre-request cleanup uses `InpDataPath` when deleting old `ai_response.json`.
- Python default `MIN_CONFIDENCE` is aligned to the frozen project value `0.65`.
- Regression tests protect the EA stale-response wait behavior and the Python safe-mode default.

## v0.26.4 Hygiene and Warning Cleanup

- Scope: project hygiene, current-entrypoint docs, and test warning cleanup only.
- Runtime code avoids deprecated `datetime.utcfromtimestamp` and deprecated `websockets.server.WebSocketServerProtocol` imports.
- `pytest.ini` pins `asyncio_default_fixture_loop_scope=function` to keep pytest-asyncio behavior stable.
- Current-facing docs point to `AI_Trader_V3.2_Integrated.mq5`; legacy EA names remain only in archive/history or explicit "do not use" notes.
- Hygiene tests guard against deprecated runtime APIs and current docs drifting back to legacy EA entrypoints.
