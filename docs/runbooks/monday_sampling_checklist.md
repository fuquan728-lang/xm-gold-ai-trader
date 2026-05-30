# Monday Forward Evidence Sampling Checklist

**Branch**: `research/v0.5.0-strategy-hypothesis-lab`  
**Last checkpoint**: `v0.5.9-no-new-market-bar-guard`  
**Status**: forward evidence collection paused (market closed Saturday)

## Pre-Sampling Verification

```powershell
cd "E:\搬家文件夹\XM Global MT5"
git status
git log --oneline -3
```

Expected: working tree clean, HEAD at `03b3969`.

## Step 1 — Verify MT5 Connection

```powershell
python -c "import MetaTrader5 as mt5; mt5.initialize(); tick = mt5.symbol_info_tick('GOLD_'); print(f'GOLD_ bid={tick.bid} ask={tick.ask} time={tick.time}'); mt5.shutdown()"
```

Expected: valid bid/ask, recent timestamp (not Friday close).

## Step 2 — Run Bounded Dry-Run Sampling

```powershell
python scripts\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 --interval-seconds 60 --max-iterations 240 --bar-close-only --json
```

## Step 3 — Check Forward Evidence Progress

```powershell
python scripts\strategy_hypothesis_lab.py --json
```

Check these 7 indicators:

| # | Indicator | Look for | Action if wrong |
|---|-----------|----------|-----------------|
| 1 | `latest_closed_bar_time` | **Advanced** beyond Friday close | If not: market may still be closed |
| 2 | `no_new_bar_journal_count` | **0** (guard cleared) | If >0: bars not advancing, stop sampling |
| 3 | `enriched_closed_bars` | **>19** | If still 19: no new evidence yet |
| 4 | `final SIGNAL` | **>0** or still 0 | If 0: keep sampling, do NOT adjust strategy |
| 5 | `diagnostics_coverage` | **>=95%** | Should remain at 100% |
| 6 | `orders_sent` | **0** | If not 0: STOP, investigate immediately |
| 7 | `safety_clean` | **true** | If false: STOP, investigate immediately |

## Step 4 — Run Pipeline Verification

```powershell
python -m pytest
python scripts\research_pipeline_verify.py --json
```

Expected: pytest passes, verify shows expected WARN only (LIVE_SIGNAL_COUNT_ZERO, ZERO_ACTIONABLE_SIGNAL_RATE).

## Decision Tree

```
bar time advanced?
  ├─ YES → guard cleared, continue monitoring bars/SIGNAL progress
  └─ NO  → market may still be closed; stop, wait, re-check later

SIGNAL count > 0?
  ├─ YES → celebrate but verify: diagnostic forensics, block reasons
  └─ NO  → keep accumulating; do NOT touch SMA, risk, or thresholds

orders_sent == 0 AND safety_clean == true?
  ├─ YES → system is healthy, continue
  └─ NO  → STOP everything, do not continue sampling
```

## ⚠️ Hard Rules

- **Do NOT relax the SMA crossover check** to force SIGNAL generation.
- **Do NOT change risk percentages or thresholds.**
- **Do NOT enable order sending.**
- **Do NOT create a new checkpoint** unless bars or SIGNAL gate status changes.
- **Do NOT merge to main.** This branch is research-only.
