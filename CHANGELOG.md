# Changelog

## v0.5.0-strategy-hypothesis-lab

- Added `scripts/strategy_hypothesis_lab.py --json`, a read-only offline
  research lab for testing why the baseline produces zero final actionable live
  dry-run signals.
- The lab evaluates historical/cached data hypotheses without touching
  production strategy defaults:
  - current SMA crossover with risk feasibility gates
  - current SMA crossover candidate-only diagnostic mode
  - alternate SMA fast/slow pairs
  - trend-continuation diagnostic mode
  - relaxed SMA-slope candidate-only diagnostic mode
- Reports candidate signal count, final theoretical signal count, signal rate,
  BUY/SELL distribution, top block reasons, minimum-lot feasibility issues, and
  comparison against the current baseline.
- Added pytest coverage proving the lab remains read-only, candidate-only
  diagnostics do not mutate production behavior, empty/missing data are handled
  safely, and no order boundary is crossed.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.6-verifier-warning-taxonomy

- Added categorized warning output to `scripts/research_pipeline_verify.py`:
  - `safety_warnings`
  - `live_sample_coverage_warnings`
  - `research_quality_warnings`
  - `strategy_signal_warnings`
  - `warning_taxonomy`
- Classified `ZERO_ACTIONABLE_SIGNAL_RATE` as a read-only strategy signal quality
  warning, not a safety violation.
- Classified `LIVE_SIGNAL_COUNT_ZERO` as a read-only research quality warning.
- Kept `final_decision: WARN` while zero final actionable signal warnings are
  present.
- Added pytest coverage proving safety warnings, sample coverage warnings, and
  strategy/research quality warnings are separated.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.5-enriched-diagnostics-sample-expansion

- Documented the expanded read-only live dry-run sample set:
  - `total_valid_journals: 129`
  - `unique_closed_bars: 121`
  - enriched SMA diagnostics recorded count: `20`
  - `fast_sma`, `slow_sma`, `previous_fast_sma`, and `previous_slow_sma`
    recorded count: `20`
  - top failed pre-signal condition: `SMA_CROSSOVER_NOT_PRESENT: 120`
  - top block reasons: `NO_ACTIONABLE_SIGNAL: 120`,
    `LOT_BELOW_VOLUME_MIN: 1`
  - `signal_count: 0`
  - zero final signal attribution remains `DOMINANT_RULE`, dominated by
    `NO_ACTIONABLE_SIGNAL`.
- Tightened read-only research reporting so `actionable_signal_rate` counts only
  final `SIGNAL` outcomes; blocked BUY/SELL candidates are now kept separate as
  candidate signal metrics.
- Added `scripts/analyze_live_sample_quality.py --json` to
  `scripts/research_pipeline_verify.py`, allowing live quality warnings such as
  `ZERO_ACTIONABLE_SIGNAL_RATE` and `LIVE_SIGNAL_COUNT_ZERO` to remain visible.
- Fixed new live dry-run diagnostics so `diagnostics.signal.stop_distance_points`
  is computed from broker `symbol.point` when possible instead of being emitted
  as a permanent `null`.
- Added tests for rejected-candidate attribution, verifier coverage, and
  enriched stop-distance diagnostics.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.4-enriched-live-sample-refresh

- Extended `scripts/analyze_live_sample_quality.py` with mixed legacy/enriched
  journal coverage reporting.
- Added `enriched_journal_count`, `legacy_journal_count`,
  `diagnostics_field_coverage`, `sma_field_availability`,
  `crossover_state_availability`, and `failed_rule_field_availability`.
- Added tests for mixed old/new journal analysis.
- Ran a short read-only enriched observation validation sample using
  `run_dry_observation_campaign.py --bar-close-only`; it generated one enriched
  journal with `diagnostics` and `orders_sent: 0`.
- Documented the full bounded 240-iteration refresh command for collecting a
  larger enriched sample set.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.3-journal-observability-enrichment

- Extended `scripts/live_dry_run_signal_journal.py` with a backward-compatible
  `diagnostics` object for new live dry-run journals.
- New diagnostics include SMA values, previous SMA values, crossover state, ATR,
  stop distance, computed lot, normalized lot, broker volume constraints,
  spread limits, failed pre-signal rules, and failed feasibility rules.
- Updated `scripts/analyze_live_sample_quality.py` to use recorded diagnostics
  when present and gracefully fall back for older journals.
- Added tests proving old journals still parse, new journals include the
  diagnostics fields, and missing legacy fields are clearly marked
  `not_recorded_in_journal`.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.2-signal-candidate-forensics

- Extended `scripts/analyze_live_sample_quality.py` with
  `signal_candidate_forensics`.
- Added per-bar diagnostics for candidate direction, confidence, signal reason,
  failed pre-signal rules, execution feasibility blockers, selected baseline
  parameters, available indicator values, risk lot forensics, and broker symbol
  constraints.
- Added aggregate counts for no-candidate bars, candidate bars, rejected
  candidates, top failed pre-signal conditions, and top execution feasibility
  blockers.
- Recorded current findings: `100` of `101` unique bars had no candidate due to
  `SMA_CROSSOVER_NOT_PRESENT`; the only `BUY` candidate was rejected by
  `LOT_BELOW_VOLUME_MIN` because computed lot was about `0.00194`, below broker
  `volume_min` of `0.01`.
- Added tests for the new forensics output.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.1-block-reason-attribution

- Extended `scripts/analyze_live_sample_quality.py` with block reason
  attribution.
- Added block reason counts and percentages, multi-reason combinations,
  candidate-to-final rejection reasons, and per-campaign block reason
  distribution.
- Added zero-final-signal attribution to classify whether the sample is blocked
  by one dominant rule or distributed filters.
- Added tests for attribution counts, percentages, multi-reason combinations,
  candidate rejection attribution, and per-campaign block reason distribution.
- Recorded current findings: `101` unique closed bars, `0` final SIGNAL
  outcomes, `1` candidate signal rejected by `LOT_BELOW_VOLUME_MIN`, and
  `NO_ACTIONABLE_SIGNAL` as the dominant block reason.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.4.0-research-quality-analysis

- Added `scripts/analyze_live_sample_quality.py` for read-only analysis of live
  dry-run sample quality.
- Summarizes valid journals, unique closed bars, final signal count, candidate
  signal count, block count/rate, top block/no-action reasons, campaign
  distribution, and closed-bar time distribution.
- Compares live sample behavior against existing historical signal replay logic
  when available.
- Added tests for the new read-only report, including safety boundary
  violations.
- Recorded current findings: `101` unique closed bars, `0` final SIGNAL
  outcomes, `1` candidate baseline signal blocked by risk controls, and
  historical expectation still normal.

No trading logic, strategy thresholds, safety checks, order routing, or AI
annotation behavior changed. No AI trading, no `order_check`, no `order_send`,
no martingale, no grid, and no lot increase after loss.

## v0.3.9-live-sample-coverage-pass

- Recorded live sample coverage PASS with `101` unique closed bars against the
  required minimum of `100`.
- Verified `python -m pytest` passes with `167` tests.
- Verified `scripts/check_live_sample_coverage.py --json` returns PASS.
- Verified `scripts/research_pipeline_verify.py --json` returns PASS.
- Documented the pytest legacy isolation fix for old V3/V4 dashboard
  interactive tests under `tests/legacy`.
- Kept default `configs/xm_gold_ai_trader.demo.yaml` order sending disabled.

No trading logic, strategy logic, safety checks, order routing, or AI annotation
behavior changed. No AI trading, no `order_check`, no `order_send`, no
martingale, no grid, and no lot increase after loss.

## v0.3.8-live-sample-collection-runbook

- Added `scripts/check_live_sample_coverage.py` for read-only sampling progress:
  current unique closed bars, remaining bars, source path, latest journal time,
  and latest closed bar time.
- Added `docs/runbooks/live_sample_collection_runbook.md` documenting bounded
  `run_dry_observation_campaign.py --bar-close-only` collection.
- Documented the target `unique_closed_bars >= 100` and
  `remaining_closed_bars == 0`.
- Kept all v0.3.7 safety and WARN semantics intact.

No AI trading, no `order_check`, no `order_send`, no martingale, no grid, and no
lot increase after loss.

## v0.3.7-live-sample-coverage

- Added explicit live sample coverage reporting to dry-run observation quality,
  live-vs-historical expectation, and research pipeline verification JSON.
- Documented that live sample coverage is counted from
  `logs/dry_run_signals/*.json`, deduplicated by closed-bar identity.
- Preserved low-sample WARN behavior for `UNIQUE_CLOSED_BARS_BELOW_MINIMUM` and
  `INSUFFICIENT_LIVE_SAMPLE`; these warnings are not hidden or converted to
  PASS.
- Added tests proving insufficient coverage still warns, sufficient coverage
  clears only live sample coverage warnings, and safety violations still block.
- Kept default `configs/xm_gold_ai_trader.demo.yaml` order sending disabled.

No AI trading, no `order_check`, no `order_send`, no martingale, no grid, and no
lot increase after loss.

## v0.3.6-research-pipeline-readonly

- Added the Phase 3 read-only research checkpoint covering baseline backtests,
  walk-forward robustness, parameter stability, live dry-run observation,
  historical replay, live-vs-historical expectation checks, and AI annotation
  auditing.
- Added research pipeline verification with `scripts/research_pipeline_verify.py`
  to run tests and read-only research checks end to end.
- Added AI annotation analysis against baseline dry-run signals while keeping AI
  commentary-only and unable to change trading decisions.
- Documented current `WARN` status: live sample coverage is still low, with no
  safety violations.
- Kept default `configs/xm_gold_ai_trader.demo.yaml` order sending disabled.

Non-goals remain unchanged: no AI trading, no `order_check` or `order_send` in
read-only research scripts, no martingale, no grid, and no lot increase after
loss.

## v0.2.6-operational-safety-hardened

- Added Phase 2.6 operational safety hardening for the demo-order workflow.
- Added runtime lock support at `.runtime/xm_gold_ai_trader.lock` with stale
  lock recovery.
- Added emergency stop file support at `.runtime/EMERGENCY_STOP` for
  order-capable scripts.
- Added one-shot daily order guard and project-magic realized daily PnL guard.
- Added MT5 history reconciliation release documentation and current
  verification commands.
- Kept default `configs/xm_gold_ai_trader.demo.yaml` order sending disabled.

Non-goals remain unchanged: no AI trading, no live account support, no
continuous auto trading, no martingale, no grid, and no lot increase after loss.
