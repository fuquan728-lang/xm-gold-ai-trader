from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dry_run_signal_report import load_dry_run_journals
from scripts.evaluate_dry_run_observation_quality import (
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
    REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM,
    timestamp_value,
    unique_closed_bar_observations,
)
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, PROJECT


MODE = "live_sample_coverage_check"


def main() -> int:
    args = parse_args()
    report = check_live_sample_coverage(
        journal_dir=Path(args.journal_dir),
        min_unique_bars=args.min_unique_bars,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def check_live_sample_coverage(*, journal_dir: Path, min_unique_bars: int = 100) -> dict[str, Any]:
    entries = load_dry_run_journals(journal_dir)
    valid_payloads = [entry["payload"] for entry in entries if entry["payload"] is not None]
    malformed_entries = [entry for entry in entries if entry["payload"] is None]
    unique_observations = unique_closed_bar_observations(valid_payloads)
    current = len(unique_observations)
    remaining = max(0, min_unique_bars - current)
    latest_payload = latest_by_timestamp(valid_payloads)
    latest_unique_payload = latest_by_timestamp(unique_observations)

    orders_sent = sum(int(payload.get("orders_sent") or 0) for payload in valid_payloads)
    order_check_called_count = sum(1 for payload in valid_payloads if bool(payload.get("order_check_called")))
    order_send_called_count = sum(1 for payload in valid_payloads if bool(payload.get("order_send_called")))

    reason_codes: list[str] = []
    reasons: list[str] = []
    if orders_sent > 0:
        add_reason(reason_codes, reasons, REASON_ORDERS_SENT_NONZERO, f"orders_sent {orders_sent} > 0")
    if order_check_called_count > 0:
        add_reason(
            reason_codes,
            reasons,
            REASON_ORDER_CHECK_CALLED,
            f"order_check_called_count {order_check_called_count} > 0",
        )
    if order_send_called_count > 0:
        add_reason(
            reason_codes,
            reasons,
            REASON_ORDER_SEND_CALLED,
            f"order_send_called_count {order_send_called_count} > 0",
        )
    if current < min_unique_bars:
        add_reason(
            reason_codes,
            reasons,
            REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM,
            f"current_unique_closed_bars {current} < required_min_unique_closed_bars {min_unique_bars}",
        )

    final_decision = "PASS"
    if any(code in reason_codes for code in (REASON_ORDERS_SENT_NONZERO, REASON_ORDER_CHECK_CALLED, REASON_ORDER_SEND_CALLED)):
        final_decision = "BLOCK"
    elif reason_codes or malformed_entries:
        final_decision = "WARN"

    return {
        "project": PROJECT,
        "mode": MODE,
        "final_decision": final_decision,
        "source_name": "dry_run_signal_journals",
        "source_path": str(journal_dir),
        "source_glob": str(journal_dir / "*.json"),
        "total_journal_files": len(entries),
        "valid_journal_files": len(valid_payloads),
        "malformed_journal_files": len(malformed_entries),
        "current_unique_closed_bars": current,
        "required_min_unique_closed_bars": min_unique_bars,
        "remaining_closed_bars": remaining,
        "sufficient_closed_bar_coverage": current >= min_unique_bars,
        "latest_journal_time_utc": latest_payload.get("timestamp_utc") if latest_payload else None,
        "latest_closed_bar_time": latest_unique_payload.get("latest_closed_bar_time") if latest_unique_payload else None,
        "orders_sent": 0,
        "observed_orders_sent_sum": orders_sent,
        "order_check_called": False,
        "order_send_called": False,
        "order_check_called_count": order_check_called_count,
        "order_send_called_count": order_send_called_count,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "collection_command": (
            "python scripts\\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 "
            "--interval-seconds 60 --max-iterations <N> --bar-close-only --json"
        ),
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
    }


def latest_by_timestamp(payloads: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if not payloads:
        return None
    return max(payloads, key=lambda payload: timestamp_value(payload.get("timestamp_utc")))


def add_reason(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    codes.append(code)
    reasons.append(f"{code}: {reason}")


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader live sample coverage")
    print(f"final_decision: {report['final_decision']}")
    print(f"source: {report['source_glob']}")
    print(f"current unique closed bars: {report['current_unique_closed_bars']}")
    print(f"required minimum: {report['required_min_unique_closed_bars']}")
    print(f"remaining closed bars: {report['remaining_closed_bars']}")
    print(f"latest journal time: {report['latest_journal_time_utc']}")
    print(f"latest closed bar: {report['latest_closed_bar_time']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check read-only live dry-run sample coverage progress.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--min-unique-bars", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
