# Checkpoint A — M5 Observation Campaign Report

**日期**: 2026-07-05 | **Campaign**: v0.25.8 | **里程碑**: v0.6.0

---

## 结果

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| total_requests | >= 30 | **214** | ✅ 超额 7x |
| matched_responses | == total_requests | **214** | ✅ 100% 匹配 |
| stale_responses_ignored | 0 | **0** | ✅ |
| timeouts | 0 | **0** | ✅ |
| trades_executed | 0 | **0** | ✅ 观察模式 |
| malformed_journals | 0 | **0** | ✅ |
| missing_required_field_journals | 0 | **0** | ✅ |

**Checkpoint A: PASSED** ✅

## AI 信号分析

| 指标 | 值 |
|------|-----|
| AI 原始 BUY 信号 | 29 (13.6%) |
| AI 原始 SELL 信号 | 3 (1.4%) |
| AI 原始 HOLD 信号 | 182 (85.0%) |
| 最终执行 BUY | 0 |
| 最终执行 SELL | 0 |
| 最终执行 HOLD | 214 (100%) |

## 阻塞原因分布

| 原因 | 次数 | 占比 |
|------|------|------|
| SPREAD_TOO_HIGH | 214 | 100% |
| ACTION_HOLD | 214 | 100% |
| LOW_CONFIDENCE | 103 | 48.1% |

## 时延分析

| 指标 | 值 |
|------|-----|
| avg_latency_ms | 2,956 ms |
| max_latency_ms | 8,323 ms |

## 结论

1. **通信协议稳定** — v0.25.7 File 模式零超时、零陈旧响应，协议冻结安全
2. **点差是唯一阻塞因素** — 100% 信号被点差 > 3.0 pips 拦截；AI 在 29 次给出了 BUY 判断（置信度合格）但全部被风控放行前的点差闸门拦截
3. **低置信度过滤有效** — 103/214 (48%) 的请求因置信度不足被 HOLD，避免低质量信号
4. **下一步** — 需完成 v0.26.0 点差制度研究（300 个观测），运行 `spread_tradeability_matrix.py` 评估替代品种/时段
