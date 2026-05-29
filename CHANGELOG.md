# Changelog

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
