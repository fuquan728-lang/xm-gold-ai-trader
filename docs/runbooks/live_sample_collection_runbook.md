# Live Sample Collection Runbook

This runbook explains how to collect enough read-only live dry-run signal
journals for `xm-gold-ai-trader` Phase 3 research checks.

The goal is to reach:

```text
unique_closed_bars >= 100
```

No command in this runbook sends orders. The collection path must remain
observation-only with `orders_sent: 0`, no `order_check`, and no `order_send`.

## Data Source

Live sample coverage is counted from:

```text
logs/dry_run_signals/*.json
```

The quality gate deduplicates valid dry-run signal journals by:

- symbol
- timeframe
- campaign id
- latest closed bar time

Campaign metadata in `logs/dry_run_campaigns/*.json` is used for supporting
diagnostics such as poll iterations and duplicate-bar skips. It is not the
primary coverage count.

## Check Current Progress

Use the read-only progress check while sampling:

```powershell
python scripts\check_live_sample_coverage.py --json
```

Useful fields:

- `current_unique_closed_bars`
- `required_min_unique_closed_bars`
- `remaining_closed_bars`
- `source_path`
- `source_glob`
- `latest_journal_time_utc`
- `latest_closed_bar_time`
- `reason_codes`

If sample coverage is still below the target, the command returns
`final_decision: WARN` with `UNIQUE_CLOSED_BARS_BELOW_MINIMUM`.

## Collect More Samples

Run bounded bar-close-only observation campaigns:

```powershell
python scripts\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 --interval-seconds 60 --max-iterations 10 --bar-close-only --json
```

Notes:

- `--bar-close-only` writes a journal only when a new closed bar is available.
- M15 bars close every 15 minutes, so a 10-minute run may produce no new unique
  bar if it starts between closes.
- Repeat this command over time until the progress check reports
  `current_unique_closed_bars >= 100`.
- Keep `max_iterations` bounded. Do not run unattended continuous trading or
  execution loops.

## Verify Research Pipeline

After collecting more samples:

```powershell
python scripts\check_live_sample_coverage.py --json
python scripts\research_pipeline_verify.py --json
```

Expected outcomes:

- If coverage remains low, `research_pipeline_verify.py` may still return
  `WARN` with `UNIQUE_CLOSED_BARS_BELOW_MINIMUM` and/or
  `INSUFFICIENT_LIVE_SAMPLE`.
- If coverage is sufficient and no other research warnings are present, the
  sample coverage WARNs clear.
- Any order activity, `order_check`, `order_send`, or forbidden AI trading
  content remains a BLOCK condition.

## Safety Invariants

These must remain true:

- Default config: `execution.allow_order_send: false`
- `orders_sent: 0`
- `order_check_called: false`
- `order_send_called: false`
- AI annotations remain read-only commentary
- No martingale
- No grid
- No automatic lot increase after loss
