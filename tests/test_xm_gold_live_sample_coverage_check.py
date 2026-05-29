from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.check_live_sample_coverage import check_live_sample_coverage
from scripts.evaluate_dry_run_observation_quality import (
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
    REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM,
)


def test_insufficient_live_sample_returns_warn(tmp_path):
    write_journal(tmp_path, "a.json", index=0)
    write_journal(tmp_path, "b.json", index=1)

    report = check_live_sample_coverage(journal_dir=tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "WARN"
    assert report["current_unique_closed_bars"] == 2
    assert report["required_min_unique_closed_bars"] == 3
    assert report["remaining_closed_bars"] == 1
    assert REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM in report["reason_codes"]
    assert report["source_path"] == str(tmp_path)
    assert report["latest_journal_time_utc"] is not None


def test_sufficient_closed_bar_coverage_clears_sample_warn(tmp_path):
    write_journal(tmp_path, "a.json", index=0)
    write_journal(tmp_path, "b.json", index=1)
    write_journal(tmp_path, "c.json", index=2)

    report = check_live_sample_coverage(journal_dir=tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "PASS"
    assert report["current_unique_closed_bars"] == 3
    assert report["remaining_closed_bars"] == 0
    assert report["reason_codes"] == []
    assert report["sufficient_closed_bar_coverage"] is True


def test_order_boundary_violation_blocks(tmp_path):
    write_journal(tmp_path, "a.json", index=0, orders_sent=1)
    write_journal(tmp_path, "b.json", index=1, order_check_called=True)
    write_journal(tmp_path, "c.json", index=2, order_send_called=True)

    report = check_live_sample_coverage(journal_dir=tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "BLOCK"
    assert REASON_ORDERS_SENT_NONZERO in report["reason_codes"]
    assert REASON_ORDER_CHECK_CALLED in report["reason_codes"]
    assert REASON_ORDER_SEND_CALLED in report["reason_codes"]
    assert report["orders_sent"] == 0
    assert report["observed_orders_sent_sum"] == 1


def write_journal(
    directory,
    filename: str,
    *,
    index: int,
    orders_sent: int = 0,
    order_check_called: bool = False,
    order_send_called: bool = False,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime(2026, 5, 28, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    payload = {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "campaign_id": "sample-coverage-test",
        "timestamp_utc": timestamp.isoformat(),
        "final_decision": "BLOCK",
        "reason_codes": ["NO_ACTIONABLE_SIGNAL"],
        "reasons": [],
        "orders_sent": orders_sent,
        "order_check_called": order_check_called,
        "order_send_called": order_send_called,
        "symbol": {"name": "GOLD_"},
        "config": {"symbol": "GOLD_"},
        "timeframe": "M15",
        "latest_closed_bar_time": str(timestamp),
        "current_spread_points": 55.0,
        "risk_preview": {"reason_codes": []},
        "signal": {"side": "HOLD"},
    }
    (directory / filename).write_text(json.dumps(payload), encoding="utf-8")
