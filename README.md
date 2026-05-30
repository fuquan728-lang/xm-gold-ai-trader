# 🚀 MT5 AI交易系统 - 企业级增强版 V3.0

> New `xm-gold-ai-trader` setup instructions are included near the end of this README.

<div align="center">

![版本](https://img.shields.io/badge/版本-V3.0-00b894)
![Python](https://img.shields.io/badge/Python-3.8+-3776ab)
![MT5](https://img.shields.io/badge/MT5-支持-00b894)
![许可证](https://img.shields.io/badge/许可证-MIT-blue)

**基于MetaTrader 5的企业级AI自动交易系统，集成DeepSeek AI智能分析**

[📚 完整文档](docs/) | [🚀 快速开始](docs/01-项目概述/QUICK_START.md) | [🏗️ 系统架构](docs/01-项目概述/ARCHITECTURE.md) | [📊 监控仪表盘](http://127.0.0.1:8000)

</div>

## ✨ 核心特性

### 🔒 企业级安全
- ✅ **持仓检查与方向验证** - 防止多空同时持仓
- ✅ **反向信号自动平仓反转** - 智能风险控制
- ✅ **止损止盈边界验证** - 确保合理交易范围
- ✅ **输入参数完整性验证** - 防止配置错误
- ✅ **每日亏损限制** - 严格的资金保护

### 🚀 高性能架构
- ✅ **四模式通信** - WebSocket/Socket/File/Auto智能切换
- ✅ **📊 Web监控界面** - 实时仪表盘 `http://127.0.0.1:8000`
- ✅ **高性能LRU缓存** - 100条记录内存缓存
- ✅ **HTTP连接池 + 自动重试** - 优化的网络通信
- ✅ **非阻塞异步架构** - 高并发请求处理
- ✅ **完整监控系统** - 全方位性能监控

### 🤖 AI智能分析
- ✅ **DeepSeek AI集成** - 先进的市场分析引擎
- ✅ **多指标综合分析** - RSI、MACD、EMA、布林带等
- ✅ **置信度评估** - 智能过滤低质量信号
- ✅ **实时市场适应** - 动态调整分析策略

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    MT5 AI交易系统 V3.0                       │
├─────────────────────────────────────────────────────────────┤
│  [MQL5 EA] ↔ [Python AI服务] ↔ [Web监控仪表盘] ↔ [数据库]     │
└─────────────────────────────────────────────────────────────┘
```

### 通信模式
- **WebSocket模式** (V3.0新增): 双向实时通信，最低延迟
- **Socket模式**: 高性能TCP通信，连接池优化
- **File模式**: 文件系统通信，最高稳定性
- **Auto模式**: 智能检测，自动故障转移

## 🚀 快速开始

### 1. 安装依赖
```powershell
pip install -r requirements.txt
```

### 2. 配置环境
```powershell
copy .env.example .env
# 编辑.env文件，设置您的DeepSeek API密钥
```

### 3. 启动服务
```powershell
python mt5_ai_service.py
```

### 4. 安装EA
- 复制 `MQL5/Experts/AI_Trader_Integrated_Socket.mq5` 到MT5
- 在MetaEditor中编译
- 添加到图表并配置参数

**详细步骤请参阅：[快速开始指南](docs/01-项目概述/QUICK_START.md)**

## 📁 项目结构

```
XM Global MT5/
├── 📄 mt5_ai_service.py          # 主服务程序（V3.0）
├── 📄 config.py                  # 配置管理系统
├── 📄 requirements.txt           # Python依赖
├── 📄 .env.example               # 环境变量模板
├── 📄 README.md                  # 本文档
│
├── 📁 docs/                      # 完整文档
│   ├── 📁 01-项目概述/          # 项目介绍和快速开始
│   ├── 📁 02-用户手册/          # 安装、配置、操作指南
│   ├── 📁 03-开发文档/          # API参考和开发指南
│   ├── 📁 04-版本历史/          # 版本发布说明
│   ├── 📁 05-技术报告/          # 技术分析和优化报告
│   └── 📁 06-参考资料/          # 术语表和最佳实践
│
├── 📁 MQL5/                      # MQL5代码
│   ├── 📁 Experts/              # EA程序
│   ├── 📁 Scripts/              # 测试脚本
│   └── 📁 Include/              # 头文件
│
├── 📁 core/                      # 核心功能模块
│   ├── ai_engine.py             # AI引擎
│   ├── cache.py                 # LRU缓存
│   ├── web_dashboard.py         # Web监控
│   └── ...                      # 其他核心模块
│
├── 📁 tests/                     # 测试套件
│   ├── test_v21.py              # V2.1安全测试
│   ├── test_socket_integration.py # Socket集成测试
│   └── ...                      # 其他测试
│
├── 📁 tools/                     # 工具脚本
│   ├── test_deepseek.py         # DeepSeek测试
│   ├── test_socket_connection.py # Socket连接测试
│   └── ...                      # 其他工具
│
└── 📁 data/                      # 数据存储
    └── trading.db               # SQLite数据库
```

## 📊 实时监控

启动服务后，访问Web监控仪表盘：
- **地址**: http://127.0.0.1:8000
- **功能**: 实时系统状态、通信模式、请求统计、性能指标

## 🔧 配置说明

### 核心配置（.env文件）
```env
# DeepSeek AI配置
USE_DEEPSEEK=true
DEEPSEEK_API_KEY=sk-您的密钥

# 服务配置
SOCKET_HOST=127.0.0.1
SOCKET_PORT=8080
WEBSOCKET_PORT=8081
HTTP_PORT=8000

# 性能配置
CACHE_SIZE=100
CONFIDENCE_THRESHOLD=0.65
REQUEST_TIMEOUT=30
```

**完整配置请参阅：[配置指南](docs/02-用户手册/CONFIGURATION.md)**

## 📚 完整文档

### 文档结构
| 目录 | 说明 | 主要文档 |
|------|------|----------|
| [📘 01-项目概述](docs/01-项目概述/) | 项目介绍和快速开始 | [快速开始](docs/01-项目概述/QUICK_START.md), [系统架构](docs/01-项目概述/ARCHITECTURE.md) |
| [📘 02-用户手册](docs/02-用户手册/) | 安装、配置、操作指南 | [安装指南](docs/02-用户手册/INSTALLATION.md), [配置说明](docs/02-用户手册/CONFIGURATION.md) |
| [📘 03-开发文档](docs/03-开发文档/) | API参考和开发指南 | [API参考](docs/03-开发文档/API_REFERENCE.md), [MQL5集成](docs/03-开发文档/MQL5_INTEGRATION.md) |
| [📘 04-版本历史](docs/04-版本历史/) | 版本发布说明 | [V2.1策略安全修复](docs/04-版本历史/V21_STRATEGY_SAFETY_FIX.md), [V2.2终极集成](docs/04-版本历史/V22_ULTIMATE_INTEGRATION.md), [V3.0企业规划](docs/04-版本历史/V30_ENTERPRISE_PLAN.md) |
| [📘 05-技术报告](docs/05-技术报告/) | 技术分析和优化报告 | [项目评审报告](docs/05-技术报告/PROJECT_REVIEW_REPORT.md), [性能优化指南](docs/05-技术报告/PERFORMANCE_OPTIMIZATION_GUIDE.md) |
| [📘 06-参考资料](docs/06-参考资料/) | 术语表和最佳实践 | [术语表](docs/06-参考资料/GLOSSARY.md), [最佳实践](docs/06-参考资料/BEST_PRACTICES.md) |

## 🐛 故障排除

常见问题请参阅：[故障排除指南](docs/02-用户手册/TROUBLESHOOTING.md)

## 🤝 贡献指南

欢迎贡献代码和文档！请参阅：[开发文档](docs/03-开发文档/)

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

<div align="center">

**✨ 从"交易系统"升级为"企业级交易平台"**

*© 2026 MT5 AI交易系统项目组*

</div>

# xm-gold-ai-trader

Safe demo-first Python 3.11 trading scaffold for XM MT5 `GOLD_`.

This addition is intentionally conservative. It does not hardcode the `GOLD_`
contract specification. The Python broker layer calls
`MetaTrader5.symbol_info("GOLD_")` before sizing, data collection, backtesting,
or execution.

## Safety Defaults

- Default mode is paper/demo. `configs/xm_gold_ai_trader.demo.yaml` has
  `execution.allow_order_send: false`.
- Any MT5 `order_send` path requires `execution.allow_order_send: true`, a demo
  account when `execution.require_demo_account: true`, and a passing `order_check`.
- No martingale, no grid, and no automatic lot increase after a loss.
- Risk controls include max daily loss, max spread, broker stop-level checks,
  step-aligned lot sizing, and one-position-only protection.
- If the calculated risk-based volume is below the broker minimum lot, the
  system blocks the trade instead of rounding up.

## XM MT5 Terminal Setup

1. Install Python 3.11 on Windows.
2. Open the XM MT5 terminal and log in to a demo account first.
3. Make sure the terminal can see the `GOLD_` symbol in Market Watch.
4. Enable algorithmic trading in MT5 only after validating paper mode.
5. Create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

6. Optionally set terminal connection values:

```powershell
$env:XM_MT5_TERMINAL_PATH="C:\Path\To\XM Global MT5\terminal64.exe"
$env:XM_GOLD_SYMBOL="GOLD_"
$env:XM_MT5_LOGIN="your-demo-login"
$env:XM_MT5_SERVER="XMGlobal-MT5 7"
$env:XM_MT5_PASSWORD="your-demo-password"
```

7. Inspect broker-provided symbol specs:

```powershell
python scripts\inspect_symbol.py --symbol GOLD_ --json
```

8. Collect reproducible bar data and symbol metadata:

```powershell
python scripts\collect_gold_data.py --symbol GOLD_ --timeframe M15 --bars 5000 --output data\gold_m15.csv
```

9. Run the baseline backtest. The script still connects to MT5 and reads
   `symbol_info("GOLD_")` for contract sizing:

```powershell
python scripts\backtest_baseline.py --input data\gold_m15.csv --output reports\baseline_backtest.json
```

10. Run one paper-trading evaluation. This script refuses to run if the config
    contains `execution.allow_order_send: true` and writes a JSONL event for audit:

```powershell
python scripts\run_paper_trader.py --json
```

## Verification Commands

Run these before any further execution work. They do not send new orders.

```powershell
python -m pytest
python scripts\phase2_verify.py
python scripts\check_live_sample_coverage.py --json
python scripts\analyze_live_sample_quality.py --json
python scripts\strategy_hypothesis_lab.py --json
python scripts\research_pipeline_verify.py --json
python scripts\evaluate_dry_run_observation_quality.py --json
python scripts\compare_live_vs_historical_signal_rate.py --json
```

Expected safety behavior:

- `phase2_verify.py` runs the always-safe verification contract and requires
  `orders_sent: 0` for dry-run and safety scripts.
- `research_pipeline_verify.py` runs pytest plus the Phase 3 read-only research
  checks. At v0.3.9 it returned `PASS` after live sample coverage reached the
  required minimum; later research-quality checkpoints may return `WARN` for
  zero final signal findings while safety remains clean.
- `check_live_sample_coverage.py` reports read-only sampling progress from
  `logs/dry_run_signals/*.json`.
- `analyze_live_sample_quality.py` reads dry-run journals and campaign metadata
  to report sample quality, final signal count, candidate signal count, block
  reasons, and historical expectation comparison. It is read-only and may
  return `WARN` for research-quality findings such as zero final `SIGNAL`
  outcomes.
- `strategy_hypothesis_lab.py` is an offline read-only research lab for
  comparing hypothetical SMA/candidate modes against historical/cached data.
  Its results are not used for production trading decisions.
- `evaluate_dry_run_observation_quality.py` and
  `compare_live_vs_historical_signal_rate.py` should keep reporting sample
  coverage details and must still block on any order execution boundary
  violation.
- AI annotation scripts are read-only commentary. They must not change source
  `final_decision`, produce trade instructions, or report forbidden trading
  fields/terms.
- A config with martingale, grid, or automatic lot increase after loss is
  invalid.

## v0.3.6 Research Pipeline Status

- Release notes:
  `docs/release_notes/v0.3.6-research-pipeline-readonly.md`.
- Default `configs/xm_gold_ai_trader.demo.yaml` has
  `execution.allow_order_send: false`.
- Phase 3 research scripts do not call `order_check` or `order_send`.
- `scripts\research_pipeline_verify.py --json` currently reports `WARN` only
  because live sample coverage is still low.
- Known strategy warnings include `STRESS_TEST_FRAGILE`, insufficient live
  sample coverage, and a low actionable live signal rate that is still
  consistent with historical expectation so far.
- AI remains read-only commentary and cannot alter trading decisions.

## v0.3.7 Live Sample Coverage

- Release notes:
  `docs/release_notes/v0.3.7-live-sample-coverage.md`.
- Live sample coverage is counted from `logs/dry_run_signals/*.json`,
  deduplicated by symbol, timeframe, campaign id, and latest closed bar time.
- `logs/dry_run_campaigns` provides supporting campaign diagnostics such as poll
  iterations and duplicate-bar skips.
- `research_pipeline_verify.py --json` now reports `live_sample_coverage` with
  current unique closed bars, required minimum bars, source path, source glob,
  and exact sample warning reason codes.
- `UNIQUE_CLOSED_BARS_BELOW_MINIMUM` and `INSUFFICIENT_LIVE_SAMPLE` remain
  visible WARNs until enough live closed-bar observations are collected.

Read-only collection command for additional live coverage:

```powershell
python scripts\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 --interval-seconds 60 --max-iterations 10 --bar-close-only --json
```

This command must remain observation-only: `orders_sent: 0`, no `order_check`,
and no `order_send`.

Progress check while sampling:

```powershell
python scripts\check_live_sample_coverage.py --json
```

Runbook:
`docs/runbooks/live_sample_collection_runbook.md`.

## v0.3.8 Live Sample Collection Runbook

- Release notes:
  `docs/release_notes/v0.3.8-live-sample-collection-runbook.md`.
- This checkpoint keeps the v0.3.7 coverage WARNs visible and adds the
  operational runbook/progress command for collecting enough read-only samples.
- Target: `unique_closed_bars >= 100` and `remaining_closed_bars == 0`.
- Do not treat this as a strategy optimization checkpoint; it is only sampling
  plumbing and read-only validation.

## v0.3.9 Live Sample Coverage Pass

- Release notes:
  `docs/release_notes/v0.3.9-live-sample-coverage-pass.md`.
- Live sample coverage reached `PASS` with `101` unique closed bars against the
  required minimum of `100`; remaining closed bars are `0`.
- Verification status:
  `python -m pytest` passes with `167` tests,
  `python scripts\check_live_sample_coverage.py --json` returns `PASS`, and
  `python scripts\research_pipeline_verify.py --json` returns `PASS`.
- Pytest legacy isolation is explicit: `tests/legacy/test_service_dashboard.py`
  is an old V3/V4 dashboard interactive test, default pytest excludes
  `legacy` and `tests/legacy`, `tests/test_xm_gold_pytest_isolation.py` locks
  that policy, and `tests/legacy/README.md` documents the legacy scope.
- Safety posture is unchanged: default `execution.allow_order_send: false`, no
  Phase 3 `order_check` or `order_send`, AI annotations remain read-only, and
  there is still no martingale, no grid, and no lot increase after loss.

## v0.4.0 Research Quality Analysis

- Release notes:
  `docs/release_notes/v0.4.0-research-quality-analysis.md`.
- Added `scripts\analyze_live_sample_quality.py --json` as a read-only research
  report over `logs\dry_run_signals\*.json` and
  `logs\dry_run_campaigns\*.json`.
- Current findings from the v0.3.9 sample set: `109` valid journals, `101`
  unique closed bars, `0` final `SIGNAL` outcomes, `1` candidate baseline signal
  blocked by risk controls, and top block reasons led by
  `NO_ACTIONABLE_SIGNAL`.
- Historical comparison remains normal with
  `LIVE_SIGNAL_RATE_WITHIN_EXPECTATION`.
- The script may return `WARN` with `LIVE_SIGNAL_COUNT_ZERO`; this is a research
  quality warning and does not change strategy behavior.
- Safety posture is unchanged: order execution disabled by default, no Phase 3
  `order_check` or `order_send`, and AI annotations remain read-only commentary.

## v0.4.1 Block Reason Attribution

- Release notes:
  `docs/release_notes/v0.4.1-block-reason-attribution.md`.
- `scripts\analyze_live_sample_quality.py --json` now includes block reason
  attribution:
  - block reason counts and percentages
  - multi-reason combinations
  - candidate-to-final rejection reasons
  - per-campaign block reason distribution
  - zero-final-signal attribution as dominant rule vs distributed filters
- Current findings from the v0.3.9/v0.4.x live sample set: `101` unique closed
  bars, `0` final `SIGNAL` outcomes, `1` candidate signal rejected by
  `LOT_BELOW_VOLUME_MIN`, and `NO_ACTIONABLE_SIGNAL` as the dominant block
  reason at about `99.01%` of blocked unique observations.
- This remains read-only research analysis. It does not change strategy
  thresholds, risk controls, order routing, or AI annotation behavior.

## v0.4.2 Signal Candidate Forensics

- Release notes:
  `docs/release_notes/v0.4.2-signal-candidate-forensics.md`.
- `scripts\analyze_live_sample_quality.py --json` now includes
  `signal_candidate_forensics` with per-bar diagnostics and aggregate counts.
- Current findings: `100` of `101` unique closed bars generated no candidate
  because `SMA_CROSSOVER_NOT_PRESENT`; the only `BUY` candidate was rejected by
  `LOT_BELOW_VOLUME_MIN`.
- The rejected BUY candidate had computed lot about `0.00194`, broker
  `volume_min` `0.01`, and normalized lot `0.0`, confirming the system did not
  round up to minimum lot.
- Raw fast/slow SMA values are not stored in current live journals, so the
  report marks those fields as `not_recorded_in_journal`; ATR is reconstructed
  from the candidate stop distance when possible.
- This remains read-only research forensics. It does not change trading logic,
  strategy thresholds, risk controls, order routing, or AI annotation behavior.

## v0.4.3 Journal Observability Enrichment

- Release notes:
  `docs/release_notes/v0.4.3-journal-observability-enrichment.md`.
- New live dry-run signal journals include a backward-compatible `diagnostics`
  object with raw SMA/ATR/crossover fields and feasibility fields.
- Recorded diagnostics include fast/slow SMA, previous fast/slow SMA, SMA
  crossover state, ATR, stop distance, computed lot, normalized lot, broker
  `volume_min`, broker `volume_step`, spread points, max allowed spread points,
  failed pre-signal rule names, and failed feasibility rule names.
- `scripts\analyze_live_sample_quality.py --json` now uses these fields when
  present and keeps parsing older journals by marking unavailable fields as
  `not_recorded_in_journal`.
- This remains observation-only research plumbing. It does not change strategy
  thresholds, risk controls, order routing, or AI annotation behavior.

## v0.4.4 Enriched Live Sample Refresh

- Release notes:
  `docs/release_notes/v0.4.4-enriched-live-sample-refresh.md`.
- `scripts\analyze_live_sample_quality.py --json` now reports mixed
  legacy/enriched diagnostics coverage:
  `enriched_journal_count`, `legacy_journal_count`,
  `diagnostics_field_coverage`, `sma_field_availability`,
  `crossover_state_availability`, and `failed_rule_field_availability`.
- A short read-only validation sample generated one enriched journal with a
  `diagnostics` object and `orders_sent: 0`.
- Current mixed sample: `110` valid journals, `1` enriched journal, `109`
  legacy journals, and `102` unique closed bars.

Full bounded enriched refresh command:

```powershell
python scripts\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 --interval-seconds 60 --max-iterations 240 --bar-close-only --json
```

This remains observation-only. It must not call `order_check`, must not call
`order_send`, and must keep `orders_sent: 0`.

## v0.4.5 Enriched Diagnostics Sample Expansion

- Release notes:
  `docs/release_notes/v0.4.5-enriched-diagnostics-sample-expansion.md`.
- Current expanded read-only sample: `129` total valid journals and `121`
  unique closed bars.
- Enriched SMA diagnostic recorded count is `20`; `fast_sma`, `slow_sma`,
  `previous_fast_sma`, and `previous_slow_sma` each have recorded count `20`.
- Top failed pre-signal condition: `SMA_CROSSOVER_NOT_PRESENT: 120`.
- Top block reasons: `NO_ACTIONABLE_SIGNAL: 120` and
  `LOT_BELOW_VOLUME_MIN: 1`.
- `signal_count` remains `0`; zero final signal attribution remains
  `DOMINANT_RULE`, dominated by `NO_ACTIONABLE_SIGNAL`.
- `actionable_signal_rate` in observation quality and live-vs-historical
  comparison now counts only final `SIGNAL` outcomes. Candidate BUY/SELL signals
  blocked by risk or feasibility gates are reported separately as candidate
  signals.
- `scripts\research_pipeline_verify.py --json` includes
  `scripts\analyze_live_sample_quality.py --json`, so live quality WARNs such as
  `ZERO_ACTIONABLE_SIGNAL_RATE` and `LIVE_SIGNAL_COUNT_ZERO` remain visible.
- This is reporting and observability only. It does not change strategy
  behavior, safety gates, order routing, `allow_order_send`, or AI annotation
  behavior.

## v0.4.6 Verifier Warning Taxonomy

- Release notes:
  `docs/release_notes/v0.4.6-verifier-warning-taxonomy.md`.
- `scripts\research_pipeline_verify.py --json` now separates WARN reasons into:
  `safety_warnings`, `live_sample_coverage_warnings`,
  `research_quality_warnings`, and `strategy_signal_warnings`.
- Current verifier status is `WARN` because final signal count is still zero,
  not because of a safety violation.
- Current classification:
  - `safety_warnings`: none
  - `live_sample_coverage_warnings`: none; coverage is `121 / 100`
  - `research_quality_warnings`: `LIVE_SIGNAL_COUNT_ZERO`
  - `strategy_signal_warnings`: `ZERO_ACTIONABLE_SIGNAL_RATE`
- `ZERO_ACTIONABLE_SIGNAL_RATE` is explicitly a read-only strategy signal
  quality warning and not a safety violation.
- This checkpoint does not change trading logic, thresholds, safety gates, order
  routing, `allow_order_send`, or AI annotation behavior.

## v0.5.0 Strategy Hypothesis Lab

- Release notes:
  `docs/release_notes/v0.5.0-strategy-hypothesis-lab.md`.
- Added `scripts\strategy_hypothesis_lab.py --json`, an offline read-only lab
  for testing candidate-generation hypotheses against collected `GOLD_` M15
  bars and cached symbol metadata.
- Hypotheses include current SMA crossover, candidate-only crossover,
  alternate SMA fast/slow pairs, trend continuation, and relaxed SMA-slope
  diagnostics.
- The report separates candidate signal count from final theoretical signal
  count and surfaces minimum-lot feasibility blockers such as
  `LOT_BELOW_VOLUME_MIN`.
- Current lab findings suggest historical crossover candidates exist, but
  risk-gated final theoretical signals are blocked by small-risk minimum-lot
  feasibility; live closed-bar samples still show candidate scarcity dominated
  by `NO_ACTIONABLE_SIGNAL`.
- This checkpoint is offline research only. It does not change production
  strategy behavior, thresholds, safety gates, order routing,
  `allow_order_send`, or AI annotation behavior.

## v0.5.1 Minimum-Lot Feasibility Study

- Release notes:
  `docs/release_notes/v0.5.1-minimum-lot-feasibility-study.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `minimum_lot_feasibility` diagnostics for `LOT_BELOW_VOLUME_MIN`.
- The report now includes computed lot, normalized lot, risk-per-lot,
  stop-distance, ATR, risk-shortfall, required account-risk amount, required
  account balance, required risk percentage, and hypothetical risk-budget
  scenario distributions.
- Current baseline finding: all `157` historical crossover candidates are below
  broker `volume_min: 0.01` at the current offline risk assumption; computed lot
  median is about `0.00168`.
- Hypothetical scenarios are explicitly labeled as research only and are not
  production settings.
- This checkpoint does not change production strategy behavior, risk settings,
  safety gates, order routing, `allow_order_send`, or AI annotation behavior.

## v0.5.2 Risk-Budget Scenario Frontier

- Release notes:
  `docs/release_notes/v0.5.2-risk-budget-scenario-frontier.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `risk_budget_frontier` under the minimum-lot feasibility study.
- The frontier tests account-balance/risk-percentage combinations:
  `$500`, `$1,000`, `$2,500`, `$5,000`, `$6,000`, `$10,000` crossed with
  `0.25%`, `0.5%`, and `1.0%`.
- It also tests fixed-dollar risk budgets: `$2.50`, `$5.00`, `$10.00`,
  `$15.00`, and `$25.00`.
- Current baseline frontier finding: fixed risk budgets of `$2.50` and `$5.00`
  make `0 / 157` historical crossover candidates feasible; `$10.00` makes
  `21 / 157` feasible; `$15.00` makes `80 / 157` feasible; `$25.00` makes
  `131 / 157` feasible.
- All rows are explicitly hypothetical/offline research. This checkpoint does
  not change production strategy behavior, risk settings, safety gates, order
  routing, `allow_order_send`, or AI annotation behavior.

## v0.5.3 Risk-Normalized Hypothesis Ranking

- Release notes:
  `docs/release_notes/v0.5.3-risk-normalized-hypothesis-ranking.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `risk_normalized_hypothesis_ranking`.
- Rankings compare existing offline hypotheses under shared fixed risk budgets:
  `$2.50`, `$5.00`, `$10.00`, `$15.00`, and `$25.00`.
- Each row reports candidates, feasible candidates, feasible percentage,
  BUY/SELL distribution, median computed/normalized lot, median stop
  distance/ATR, median risk shortfall, and blockers.
- The scoring model emphasizes feasibility percentage and penalizes raw
  candidate spam, so a high-candidate hypothesis is not automatically ranked
  best.
- Current top ranked hypothesis across tested fixed budgets is
  `current_baseline_risk_gated`, mainly because it is risk-gated, balanced, and
  avoids the candidate-spam penalty.
- This checkpoint is offline research only. It does not change production
  strategy behavior, risk settings, safety gates, order routing,
  `allow_order_send`, or AI annotation behavior.

## v0.5.4 Hypothesis Selection Evidence Pack

- Release notes:
  `docs/release_notes/v0.5.4-hypothesis-selection-evidence-pack.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `hypothesis_selection_evidence_pack`.
- The evidence pack summarizes baseline candidate feasibility, minimum-lot
  bottlenecks, risk-budget frontier results, normalized rankings, top ranked
  hypotheses by budget, and why `current_baseline_risk_gated` remains preferred
  offline.
- It explicitly reports that production is not ready:
  `production_strategy_change_recommended: false`,
  `live_order_enablement_recommended: false`, and
  `ai_trading_behavior_introduced: false`.
- It records why raw candidate spam is penalized and why
  `sma_10_30_risk_gated` is not selected yet despite being close at the `$25`
  hypothetical risk budget.
- Next evidence required includes longer enriched live samples,
  out-of-sample validation, drawdown/MAE/MFE analysis, spread regime
  sensitivity, realistic minimum-lot feasibility, and forward dry-run evidence.
- This checkpoint is offline research only. It does not change production
  strategy behavior, risk settings, safety gates, order routing,
  `allow_order_send`, or AI annotation behavior.

## v0.5.5 Forward Evidence Plan

- Release notes:
  `docs/release_notes/v0.5.5-forward-evidence-plan.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `forward_evidence_plan`.
- v0.6 parameter-candidate research is gated on at least `500` enriched
  closed-bar dry-run observations, at least `5` final dry-run `SIGNAL`
  observations, and at least `95%` diagnostics coverage.
- The plan requires a chronological train/test out-of-sample split with no
  parameter selection on the test split.
- Risk feasibility must be reported under realistic account/risk assumptions
  and broker constraints including `volume_min` and `volume_step`.
- Future evidence must cover spread regimes, ATR/volatility regimes,
  stop-distance distributions, MAE/MFE if available, drawdown proxy, BUY/SELL
  balance, and raw candidate spam penalty.
- Production remains explicitly disabled:
  `production_strategy_change_recommended: false` and
  `live_order_enablement_recommended: false`.
- This checkpoint is planning only. It does not change production strategy
  behavior, risk settings, safety gates, order routing, `allow_order_send`, or
  AI annotation behavior.

## v0.5.6 Forward Sample Collection Plan

- Release notes:
  `docs/release_notes/v0.5.6-forward-sample-collection-plan.md`.
- Extended `scripts\strategy_hypothesis_lab.py --json` with
  `forward_sample_collection_plan`.
- Converted v0.5.5 forward evidence gates into an executable read-only
  sampling plan with progress tracking.
- Each gate reports `current`, `required`, `remaining`, and `met`:
  enriched closed bars (target: `500`), final dry-run SIGNALs (target: `5`),
  diagnostics coverage (target: `95%`).
- Gates default to zero/unmet — no gate is treated as passed by accident.
- Included recommended sampling command with bounded, bar-close-only parameters
  and explicit cadence rules.
- Defined what passing all gates unlocks (v0.6 offline parameter-candidate
  research) and what remains blocked (production strategy changes, live order
  enablement).
- Current progress: `19 / 500` enriched closed bars, `0 / 5` final SIGNALs,
  `100%` diagnostics coverage (forward window only, 109 legacy excluded).
- This checkpoint is planning only. It does not change production strategy
  behavior, risk settings, safety gates, order routing, `allow_order_send`, or
  AI annotation behavior.

## v0.5.7 Forward Window Metrics Fix

- Release notes:
  `docs/release_notes/v0.5.7-forward-window-metrics-fix.md`.
- Fixed diagnostics coverage denominator: only counts enriched journals
  (schema_version >= 1), excludes 109 legacy pre-enrichment journals.
- Added `_collect_forward_window_stats()` to read only enriched journals
  and compute real forward window metrics: enriched journal count, legacy
  exclusion count, closed bars, final SIGNAL count, coverage, and top blocks.
- Forward window metrics are now live from `logs/dry_run_signals/*.json`
  instead of hardcoded zeros.
- Current forward window: `21` enriched journals, `19` unique closed bars,
  `0` final SIGNALs, `100%` diagnostics coverage, `SMA_CROSSOVER_NOT_PRESENT`
  dominant block reason, gates not met.
- Updated `run_strategy_hypothesis_lab()` with optional `journal_glob` for
  test isolation.
- This is a read-only metrics calculation fix. It does not change production
  strategy behavior, risk settings, safety gates, order routing,
  `allow_order_send`, or AI annotation behavior.

## v0.5.8 Repository Hygiene Cleanup

- Release notes:
  `docs/release_notes/v0.5.8-repository-hygiene-cleanup.md`.
- Low-risk repository hygiene checkpoint. Moved 17 stale/broken legacy
  files to archive directories. No active code or production behavior changed.
- Moved 8 root-level markdown files (stale Chinese reports + obsolete tech
  docs) to `docs/archive/obsolete/`.
- Moved 6 `docs/05-技术报告/` files referencing deleted modules
  (`ai_file_server.py`, `ai_engine_enhanced.py`, `mql5_finance_data.py`)
  to archive.
- Created `docs/MQL5_EA_VERSION_INVENTORY.md` documenting active/legacy EA
  versions. No EA files deleted.
- Created `docs/backlog/repository_integration_candidates.md` listing 6
  integration candidates for future review.
- Created `legacy_v4/tests/README.md` documenting 14 legacy tests including
  1 broken test.
- Moved `run_test_capture.py` and `remove_emoji.py` (broken path references)
  to `archive/obsolete_tools/`.
- No strategy, risk, safety, order routing, or AI annotation changes.

## v0.5.9 No-New-Market-Bar Guard

- Release notes:
  `docs/release_notes/v0.5.9-no-new-market-bar-guard.md`.
- Added `market_bar_guard` to forward sample collection plan — detects when
  `latest_closed_bar_time` has not advanced across enriched journals.
- Journals with duplicate bar time are flagged as `NO_NEW_MARKET_BAR` and
  explicitly excluded from forward evidence counts.
- Reports `no_new_bar_journal_count`, `market_advancing`,
  `weekend_or_market_closed_possible`, and affected campaign IDs.
- Current detection: 3 duplicate-bar journals from 2 weekend campaigns.
- Prevents weekend/cached bar confusion without changing strategy, risk,
  safety, order routing, or AI annotation behavior.

## v0.2.6 Operational Safety Guarantees

- Default `configs/xm_gold_ai_trader.demo.yaml` has
  `execution.allow_order_send: false`.
- Runtime lock: `.runtime/xm_gold_ai_trader.lock` blocks overlapping
  order-capable runs and supports stale lock recovery.
- Emergency stop file: `.runtime/EMERGENCY_STOP` blocks order-capable scripts.
- One-shot guard blocks a second accepted project `GOLD_` demo order on the same
  day when `execution.one_shot_only: true`.
- Daily loss guard blocks after project-magic `GOLD_` realized loss exceeds
  `risk.max_daily_loss_pct`.
- Demo micro orders require explicit manual and environment confirmation in the
  one-shot demo-order config.
- Demo order journals use schema v1 and are reconciled against MT5 history.

Release notes: `docs/release_notes/v0.2.6-operational-safety-hardened.md`.

## New Project Files

- `src/broker/mt5_client.py`: MT5 connection, live symbol inspection, account,
  position, history, rates, order-check, and checked order-send wrapper.
- `src/broker/execution_safety.py`: account-level execution gates and stable
  reason codes for Phase 2.
- `src/broker/order_executor.py`: demo-first execution gate. Order sending is
  blocked unless `execution.allow_order_send: true` and `order_check` passed.
- `src/strategy/risk_manager.py`: lot sizing and risk limits.
- `src/strategy/baseline_signal.py`: reproducible SMA/ATR baseline signal.
- `scripts/inspect_symbol.py`: prints current XM `GOLD_` symbol info.
- `scripts/collect_gold_data.py`: exports MT5 bars and symbol metadata.
- `scripts/backtest_baseline.py`: baseline backtest with current MT5 contract
  specs.
- `scripts/smoke_check.py`: read-only MT5/account/symbol/config verification.
- `scripts/dry_run_signal.py`: read-only baseline signal and risk decision check
  that never calls `order_send`.
- `scripts/preflight_order_check.py`: computes a candidate baseline trade and
  runs local gates plus `order_check` only.
- `scripts/demo_micro_order.py`: controlled demo-only micro-order workflow.
- `scripts/close_demo_positions.py`: closes only matching project-magic demo
  `GOLD_` positions after `order_check`.
- `scripts/run_paper_trader.py`: one-shot paper trading runner with journaled
  signal, risk, account, tick, and execution status.
- `MQL5/Experts/XM_Gold_AI_Trader_SafetyGuard.mq5`: read-only chart monitor
  that displays dynamic `GOLD_` symbol/account safety status and never sends orders.
- `tests/test_xm_gold_risk_manager.py`: lot sizing and risk-limit tests.
- `logs/.gitkeep`: keeps the log directory present for local verification logs.
