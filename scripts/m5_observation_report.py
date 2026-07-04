from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.observation_journal import DEFAULT_JOURNAL_DIR, iter_observations, summarize_observations


def main() -> int:
    args = parse_args()
    report = summarize_observations(
        iter_observations(args.journal_dir),
        symbol=args.symbol,
        timeframe=args.timeframe,
        target=args.target,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print_summary(report)
    return 0


def print_summary(report: dict) -> None:
    print("xm-gold-ai-trader M5 observation report")
    print(f"campaign: {report['campaign_version']}")
    print(f"symbol/timeframe: {report['symbol']} {report['timeframe']}")
    print(f"total_requests: {report['total_requests']}")
    print(f"matched_responses: {report['matched_responses']}")
    print(f"stale_responses_ignored: {report['stale_responses_ignored']}")
    print(f"timeouts: {report['timeouts']}")
    print(
        "ai_action_raw BUY/SELL/HOLD: "
        f"{report['ai_action_raw_BUY']}/{report['ai_action_raw_SELL']}/{report['ai_action_raw_HOLD']}"
    )
    print(
        "final_action BUY/SELL/HOLD: "
        f"{report['final_action_BUY']}/{report['final_action_SELL']}/{report['final_action_HOLD']}"
    )
    print(f"blocked_by_ACTION_HOLD: {report['blocked_by_ACTION_HOLD']}")
    print(f"blocked_by_LOW_CONFIDENCE: {report['blocked_by_LOW_CONFIDENCE']}")
    print(f"blocked_by_SPREAD_TOO_HIGH: {report['blocked_by_SPREAD_TOO_HIGH']}")
    print(f"blocked_by_SAFETY_GATE: {report['blocked_by_SAFETY_GATE']}")
    print(f"trades_executed: {report['trades_executed']}")
    print(f"avg_latency_ms: {report['avg_latency_ms']}")
    print(f"max_latency_ms: {report['max_latency_ms']}")
    print(f"malformed_journals: {report['malformed_journals']}")
    print(f"missing_required_field_journals: {report['missing_required_field_journals']}")
    print(f"checkpoint_pass: {report['checkpoint_pass']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize v0.25.8 M5 observation journals.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--symbol", default="GOLD_")
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--target", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
