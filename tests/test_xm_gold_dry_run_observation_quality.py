from __future__ import annotations

import json

from scripts.dry_run_signal_report import REASON_JOURNAL_JSON_INVALID
from scripts.evaluate_dry_run_observation_quality import (
    REASON_MAX_SPREAD_THRESHOLD_EXCEEDED,
    REASON_OBSERVATIONS_SINGLE_SESSION,
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
    REASON_TOO_MANY_MALFORMED_JOURNALS,
    REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM,
    REASON_ZERO_ACTIONABLE_SIGNAL_RATE,
    evaluate_observation_quality,
)


def test_blocks_on_orders_sent_nonzero(tmp_path):
    write_observation(tmp_path, "a.json", orders_sent=1, final_decision="SIGNAL", side="BUY")

    report = evaluate(tmp_path, min_unique_bars=1)

    assert report["final_decision"] == "BLOCK"
    assert REASON_ORDERS_SENT_NONZERO in report["reason_codes"]
    assert report["orders_sent"] > 0


def test_blocks_on_order_check_called_true(tmp_path):
    write_observation(tmp_path, "a.json", order_check_called=True, final_decision="SIGNAL", side="BUY")

    report = evaluate(tmp_path, min_unique_bars=1)

    assert report["final_decision"] == "BLOCK"
    assert REASON_ORDER_CHECK_CALLED in report["reason_codes"]
    assert report["order_check_called_count"] == 1


def test_blocks_on_order_send_called_true(tmp_path):
    write_observation(tmp_path, "a.json", order_send_called=True, final_decision="SIGNAL", side="BUY")

    report = evaluate(tmp_path, min_unique_bars=1)

    assert report["final_decision"] == "BLOCK"
    assert REASON_ORDER_SEND_CALLED in report["reason_codes"]
    assert report["order_send_called_count"] == 1


def test_warns_below_min_unique_bars(tmp_path):
    write_observation(tmp_path, "a.json", closed_bar="2026-05-27 00:00:00+00:00", final_decision="SIGNAL", side="BUY")
    write_observation(tmp_path, "b.json", closed_bar="2026-05-27 08:00:00+00:00", final_decision="SIGNAL", side="SELL")

    report = evaluate(tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "WARN"
    assert REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM in report["reason_codes"]
    assert report["unique_closed_bars"] == 2
    assert report["live_sample_coverage"]["current_unique_closed_bars"] == 2
    assert report["live_sample_coverage"]["required_min_unique_closed_bars"] == 3
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is False
    assert REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM in report["live_sample_coverage"]["warn_reason_codes"]


def test_warns_all_observations_from_one_session(tmp_path):
    write_observation(tmp_path, "a.json", closed_bar="2026-05-27 08:00:00+00:00", final_decision="SIGNAL", side="BUY")
    write_observation(tmp_path, "b.json", closed_bar="2026-05-27 09:00:00+00:00", final_decision="SIGNAL", side="SELL")

    report = evaluate(tmp_path, min_unique_bars=2)

    assert report["final_decision"] == "WARN"
    assert REASON_OBSERVATIONS_SINGLE_SESSION in report["reason_codes"]


def test_warns_max_spread_exceeded(tmp_path):
    write_clean_observation_set(tmp_path, spread=400.0)

    report = evaluate(tmp_path, min_unique_bars=3, max_spread_points=350.0)

    assert report["final_decision"] == "WARN"
    assert REASON_MAX_SPREAD_THRESHOLD_EXCEEDED in report["reason_codes"]
    assert report["max_spread"] == 400.0


def test_passes_clean_observation_set(tmp_path):
    write_clean_observation_set(tmp_path)

    report = evaluate(tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "PASS"
    assert report["reason_codes"] == []
    assert report["orders_sent"] == 0
    assert report["order_check_called_count"] == 0
    assert report["order_send_called_count"] == 0
    assert report["unique_closed_bars"] == 3
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is True
    assert report["live_sample_coverage"]["warn_reason_codes"] == []


def test_rejected_candidate_does_not_clear_zero_actionable_signal_warn(tmp_path):
    write_observation(
        tmp_path,
        "candidate-blocked.json",
        final_decision="BLOCK",
        side="BUY",
        reason_codes=["LOT_BELOW_VOLUME_MIN"],
    )

    report = evaluate(tmp_path, min_unique_bars=1)

    assert report["final_decision"] == "WARN"
    assert REASON_ZERO_ACTIONABLE_SIGNAL_RATE in report["reason_codes"]
    assert report["actionable_signal_rate"] == 0.0
    assert report["buy_signal_count"] == 0
    assert report["candidate_signal_count"] == 1
    assert report["candidate_buy_signal_count"] == 1


def test_handles_malformed_journals_safely(tmp_path):
    write_clean_observation_set(tmp_path)
    journal_dir = tmp_path / "journals"
    (journal_dir / "bad.json").write_text("{bad", encoding="utf-8")

    report = evaluate(tmp_path, min_unique_bars=3)

    assert report["final_decision"] == "WARN"
    assert REASON_TOO_MANY_MALFORMED_JOURNALS in report["reason_codes"]
    assert report["reason_code_counts"][REASON_JOURNAL_JSON_INVALID] == 1
    assert report["malformed_journals"] == 1


def evaluate(tmp_path, *, min_unique_bars: int, max_spread_points: float = 350.0):
    return evaluate_observation_quality(
        journal_dir=tmp_path / "journals",
        campaign_dir=tmp_path / "campaigns",
        min_unique_bars=min_unique_bars,
        max_spread_points=max_spread_points,
    )


def write_clean_observation_set(tmp_path, *, spread: float = 55.0) -> None:
    write_observation(
        tmp_path,
        "asia.json",
        timestamp="2026-05-27T01:00:00+00:00",
        closed_bar="2026-05-27 01:00:00+00:00",
        final_decision="SIGNAL",
        side="BUY",
        spread=spread,
    )
    write_observation(
        tmp_path,
        "london.json",
        timestamp="2026-05-27T08:00:00+00:00",
        closed_bar="2026-05-27 08:00:00+00:00",
        final_decision="BLOCK",
        side="HOLD",
        reason_codes=["NO_ACTIONABLE_SIGNAL"],
        spread=spread,
    )
    write_observation(
        tmp_path,
        "newyork.json",
        timestamp="2026-05-27T13:00:00+00:00",
        closed_bar="2026-05-27 13:00:00+00:00",
        final_decision="SIGNAL",
        side="SELL",
        spread=spread,
    )
    write_campaign(tmp_path, total_poll_iterations=3)


def write_observation(
    tmp_path,
    filename: str,
    *,
    timestamp: str = "2026-05-27T08:00:00+00:00",
    closed_bar: str = "2026-05-27 08:00:00+00:00",
    final_decision: str = "BLOCK",
    side: str = "HOLD",
    reason_codes: list[str] | None = None,
    spread: float = 55.0,
    orders_sent: int = 0,
    order_check_called: bool = False,
    order_send_called: bool = False,
) -> None:
    journal_dir = tmp_path / "journals"
    journal_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "campaign_id": "campaign-quality",
        "timestamp_utc": timestamp,
        "final_decision": final_decision,
        "reason_codes": reason_codes or [],
        "reasons": [],
        "orders_sent": orders_sent,
        "order_check_called": order_check_called,
        "order_send_called": order_send_called,
        "symbol": {"name": "GOLD_"},
        "config": {"symbol": "GOLD_"},
        "timeframe": "M15",
        "latest_closed_bar_time": closed_bar,
        "current_spread_points": spread,
        "risk_preview": {"reason_codes": reason_codes or []},
        "signal": {"side": side},
    }
    (journal_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def write_campaign(tmp_path, *, total_poll_iterations: int) -> None:
    campaign_dir = tmp_path / "campaigns"
    campaign_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "dry_observation_campaign",
        "campaign_id": "campaign-quality",
        "total_poll_iterations": total_poll_iterations,
        "journal_count": total_poll_iterations,
        "duplicate_bar_skipped": 0,
        "orders_sent": 0,
        "observed_orders_sent_sum": 0,
    }
    (campaign_dir / "campaign-quality.json").write_text(json.dumps(payload), encoding="utf-8")
