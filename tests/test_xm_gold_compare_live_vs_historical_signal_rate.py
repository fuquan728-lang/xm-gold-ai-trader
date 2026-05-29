from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from scripts.compare_live_vs_historical_signal_rate import (
    REASON_HIGH_LIVE_SIGNAL_RATE,
    REASON_INSUFFICIENT_LIVE_SAMPLE,
    REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION,
    REASON_LOW_LIVE_SIGNAL_RATE,
    compare_live_vs_historical,
    evaluate_expectation,
)


def test_zero_live_signals_with_29_bars_is_insufficient_not_failure():
    report = compare_live_vs_historical(
        historical_report=historical_report(rate=0.0314, signals=157, total=5_000),
        live_payloads=live_payloads(total=29, signals=0),
        min_live_bars=100,
    )

    assert report["expectation_result"] == "NORMAL"
    assert REASON_INSUFFICIENT_LIVE_SAMPLE in report["reason_codes"]
    assert REASON_LOW_LIVE_SIGNAL_RATE not in report["reason_codes"]
    assert report["live_bars_observed"] == 29
    assert report["actual_live_signals"] == 0
    assert report["orders_sent"] == 0
    assert report["live_sample_coverage"]["current_unique_closed_bars"] == 29
    assert report["live_sample_coverage"]["required_min_unique_closed_bars"] == 100
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is False
    assert REASON_INSUFFICIENT_LIVE_SAMPLE in report["live_sample_coverage"]["warn_reason_codes"]


def test_zero_live_signals_after_large_sample_warns():
    expectation = evaluate_expectation(
        historical_actionable_signal_rate=0.0314,
        live_bars_observed=500,
        actual_live_signals=0,
        min_live_bars=100,
        tolerance_z=3.0,
    )

    assert expectation["expectation_result"] == "LOW_SIGNAL_WARNING"
    assert expectation["reason_codes"] == [REASON_LOW_LIVE_SIGNAL_RATE]
    assert expectation["expected_live_signals"] == pytest.approx(15.7)


def test_high_live_signal_rate_warns():
    expectation = evaluate_expectation(
        historical_actionable_signal_rate=0.0314,
        live_bars_observed=500,
        actual_live_signals=80,
        min_live_bars=100,
        tolerance_z=3.0,
    )

    assert expectation["expectation_result"] == "HIGH_SIGNAL_WARNING"
    assert expectation["reason_codes"] == [REASON_HIGH_LIVE_SIGNAL_RATE]


def test_signal_rate_within_expectation_is_normal():
    expectation = evaluate_expectation(
        historical_actionable_signal_rate=0.0314,
        live_bars_observed=500,
        actual_live_signals=16,
        min_live_bars=100,
        tolerance_z=3.0,
    )

    assert expectation["expectation_result"] == "NORMAL"
    assert expectation["reason_codes"] == [REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION]


def test_comparison_report_never_reports_order_check_or_order_send():
    report = compare_live_vs_historical(
        historical_report=historical_report(rate=0.0314, signals=157, total=5_000),
        live_payloads=live_payloads(total=120, signals=4),
        min_live_bars=100,
    )

    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False
    assert report["hard_safety"]["order_check"] is False
    assert report["hard_safety"]["order_send"] is False
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is True


def historical_report(*, rate: float, signals: int, total: int) -> dict:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "historical_signal_replay",
        "total_observations": total,
        "total_bars_replayed": total,
        "signal_count": signals,
        "buy_signal_count": signals // 2,
        "sell_signal_count": signals - (signals // 2),
        "actionable_signal_rate": rate,
        "diagnostics": {"average_bars_between_signals": 31.26923076923077},
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
    }


def live_payloads(*, total: int, signals: int) -> list[dict]:
    start = datetime(2026, 5, 27, tzinfo=timezone.utc)
    payloads = []
    for index in range(total):
        is_signal = index < signals
        side = "BUY" if index % 2 == 0 else "SELL"
        closed_bar = start + timedelta(minutes=15 * index)
        payloads.append(
            {
                "journal_schema_version": 1,
                "project": "xm-gold-ai-trader",
                "mode": "live_dry_run_signal_journal",
                "campaign_id": "compare-test",
                "timestamp_utc": closed_bar.isoformat(),
                "final_decision": "SIGNAL" if is_signal else "BLOCK",
                "reason_codes": [] if is_signal else ["NO_ACTIONABLE_SIGNAL"],
                "reasons": [],
                "orders_sent": 0,
                "order_check_called": False,
                "order_send_called": False,
                "symbol": {"name": "GOLD_"},
                "config": {"symbol": "GOLD_"},
                "timeframe": "M15",
                "latest_closed_bar_time": str(closed_bar),
                "current_spread_points": 55.0,
                "risk_preview": {"reason_codes": []},
                "signal": {"side": side if is_signal else "HOLD"},
            }
        )
    return payloads
