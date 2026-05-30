from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.analyze_live_sample_quality import (
    REASON_LIVE_SIGNAL_COUNT_ZERO,
    REASON_MALFORMED_LIVE_JOURNALS,
    analyze_live_sample_quality,
)
from scripts.compare_live_vs_historical_signal_rate import REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION
from scripts.evaluate_dry_run_observation_quality import (
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
)


def test_live_quality_report_summarizes_zero_signal_samples(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_campaign(campaign_dir, "campaign-a", duplicate_bar_skipped=2)
    for index in range(3):
        write_journal(journal_dir, f"journal-{index}.json", index=index, campaign_id="campaign-a")

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    assert report["total_valid_journals"] == 3
    assert report["unique_closed_bars"] == 3
    assert report["signal_count"] == 0
    assert report["block_count"] == 3
    assert report["zero_signal_across_live_samples"] is True
    assert REASON_LIVE_SIGNAL_COUNT_ZERO in report["reason_codes"]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False
    attribution = report["block_reason_attribution"]
    assert attribution["block_reason_counts"] == {"NO_ACTIONABLE_SIGNAL": 3}
    assert attribution["block_reason_percentages"]["NO_ACTIONABLE_SIGNAL"] == 1.0
    assert attribution["zero_final_signal_attribution"]["classification"] == "DOMINANT_RULE"
    assert attribution["zero_final_signal_attribution"]["one_dominant_rule"] is True
    forensics = report["signal_candidate_forensics"]
    assert forensics["no_candidate_generated"] == 3
    assert forensics["candidate_generated"] == 0
    assert forensics["top_failed_pre_signal_conditions"][0]["reason"] == "SMA_CROSSOVER_NOT_PRESENT"


def test_live_quality_report_includes_campaign_and_closed_bar_distribution(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_campaign(campaign_dir, "campaign-a")
    write_campaign(campaign_dir, "campaign-b")
    write_journal(journal_dir, "a.json", index=0, campaign_id="campaign-a", final_decision="SIGNAL", side="BUY")
    write_journal(journal_dir, "b.json", index=1, campaign_id="campaign-b")

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    by_campaign = {item["campaign_id"]: item for item in report["distribution_by_campaign"]}
    assert by_campaign["campaign-a"]["signal_count"] == 1
    assert by_campaign["campaign-b"]["block_count"] == 1
    assert len(report["distribution_by_closed_bar_time"]) == 2
    assert report["distribution_by_closed_bar_time"][0]["observation_count"] == 1


def test_block_reason_attribution_counts_percentages_and_combinations(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_journal(journal_dir, "a.json", index=0, reason_codes=["NO_ACTIONABLE_SIGNAL"])
    write_journal(journal_dir, "b.json", index=1, reason_codes=["SPREAD_TOO_HIGH"])
    write_journal(journal_dir, "c.json", index=2, reason_codes=["NO_ACTIONABLE_SIGNAL", "SPREAD_TOO_HIGH"])

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    attribution = report["block_reason_attribution"]
    assert attribution["block_count"] == 3
    assert attribution["block_reason_counts"] == {
        "NO_ACTIONABLE_SIGNAL": 2,
        "SPREAD_TOO_HIGH": 2,
    }
    assert attribution["block_reason_percentages"]["NO_ACTIONABLE_SIGNAL"] == 2 / 3
    assert attribution["block_reason_percentages"]["SPREAD_TOO_HIGH"] == 2 / 3
    assert attribution["multi_reason_combinations"] == [
        {
            "reason_codes": ["NO_ACTIONABLE_SIGNAL", "SPREAD_TOO_HIGH"],
            "count": 1,
            "percentage": 1 / 3,
        }
    ]
    assert attribution["zero_final_signal_attribution"]["classification"] == "DISTRIBUTED_FILTERS"


def test_candidate_to_final_rejection_reason_is_attributed(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_journal(
        journal_dir,
        "candidate-blocked.json",
        index=0,
        side="BUY",
        reason_codes=["LOT_BELOW_VOLUME_MIN"],
        reasons=["LOT_BELOW_VOLUME_MIN: calculated volume below broker minimum"],
    )

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    rejection = report["candidate_to_final_rejection"]
    assert rejection["total_candidate_signals"] == 1
    assert rejection["candidate_rejection_count"] == 1
    assert rejection["candidate_rejection_rate"] == 1.0
    assert rejection["reason_counts"] == {"LOT_BELOW_VOLUME_MIN": 1}
    assert rejection["by_side"]["BUY"]["reason_counts"] == {"LOT_BELOW_VOLUME_MIN": 1}
    forensics = report["signal_candidate_forensics"]
    assert forensics["candidate_generated"] == 1
    assert forensics["candidate_generated_but_rejected"] == 1
    assert forensics["top_execution_feasibility_blockers"][0]["reason"] == "LOT_BELOW_VOLUME_MIN"
    bar = forensics["per_bar_diagnostics"][0]
    assert bar["candidate_direction"] == "BUY"
    assert bar["confidence"] == 0.55
    assert bar["risk_lot_forensics"]["volume_min"] == 0.01
    assert bar["risk_lot_forensics"]["computed_lot"] == 0.002
    assert bar["risk_lot_forensics"]["normalized_lot"] == 0.0
    assert bar["risk_lot_forensics"]["risk_shortfall_to_min_lot"] == 10.0
    assert bar["symbol_constraints"]["volume_min"] == 0.01
    assert bar["indicator_values"]["availability"]["fast_sma"] == "not_recorded_in_journal"
    assert bar["indicator_values"]["atr_price_reconstructed"] == 10.0


def test_report_uses_recorded_diagnostics_when_present(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_journal(
        journal_dir,
        "diagnostic-candidate.json",
        index=0,
        side="BUY",
        reason_codes=["LOT_BELOW_VOLUME_MIN"],
        reasons=["LOT_BELOW_VOLUME_MIN: calculated volume below broker minimum"],
        diagnostics=diagnostics_payload(),
    )

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    bar = report["signal_candidate_forensics"]["per_bar_diagnostics"][0]
    assert bar["failed_rule_names"] == ["LOT_BELOW_VOLUME_MIN"]
    assert bar["indicator_values"]["availability"]["fast_sma"] == "recorded_in_journal"
    assert bar["indicator_values"]["fast_sma"] == 101.5
    assert bar["indicator_values"]["previous_fast_sma"] == 99.0
    assert bar["indicator_values"]["sma_crossover_state"] == "CROSSED_UP"
    assert bar["indicator_values"]["atr"] == 8.5
    assert bar["risk_lot_forensics"]["computed_lot"] == 0.0019
    assert bar["risk_lot_forensics"]["normalized_lot"] == 0.0
    assert bar["symbol_constraints"]["max_spread_points"] == 350.0


def test_mixed_old_and_new_journals_report_diagnostics_coverage(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_journal(journal_dir, "legacy.json", index=0)
    write_journal(
        journal_dir,
        "enriched.json",
        index=1,
        side="BUY",
        reason_codes=["LOT_BELOW_VOLUME_MIN"],
        diagnostics=diagnostics_payload(),
    )

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    assert report["total_valid_journals"] == 2
    assert report["enriched_journal_count"] == 1
    assert report["legacy_journal_count"] == 1
    assert report["diagnostics_field_coverage"]["diagnostics"]["recorded_pct"] == 0.5
    assert report["diagnostics_field_coverage"]["fast_sma"]["recorded_count"] == 1
    assert report["sma_field_availability"]["slow_sma"]["not_recorded_count"] == 1
    assert report["crossover_state_availability"]["state_counts"] == {"CROSSED_UP": 1}
    assert report["failed_rule_field_availability"]["both_failed_rule_fields_recorded"] == 1


def test_per_campaign_block_reason_distribution_is_reported(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_campaign(campaign_dir, "campaign-a")
    write_campaign(campaign_dir, "campaign-b")
    write_journal(journal_dir, "a.json", index=0, campaign_id="campaign-a", reason_codes=["NO_ACTIONABLE_SIGNAL"])
    write_journal(journal_dir, "b.json", index=1, campaign_id="campaign-b", reason_codes=["SPREAD_TOO_HIGH"])

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    by_campaign = {
        item["campaign_id"]: item
        for item in report["per_campaign_block_reason_distribution"]
    }
    assert by_campaign["campaign-a"]["block_reason_counts"] == {"NO_ACTIONABLE_SIGNAL": 1}
    assert by_campaign["campaign-b"]["block_reason_counts"] == {"SPREAD_TOO_HIGH": 1}


def test_live_quality_report_compares_against_existing_historical_replay(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.0314, signals=157, total=5_000)
    for index in range(120):
        is_signal = index < 4
        write_journal(
            journal_dir,
            f"journal-{index}.json",
            index=index,
            final_decision="SIGNAL" if is_signal else "BLOCK",
            side="BUY" if is_signal else "HOLD",
        )

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        min_live_bars=100,
        build_historical_if_missing=False,
    )

    comparison = report["historical_comparison"]
    assert comparison["available"] is True
    assert comparison["actual_live_signals"] == 4
    assert comparison["live_bars_observed"] == 120
    assert REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION in comparison["reason_codes"]


def test_live_quality_report_blocks_on_order_boundary_violations(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    write_journal(
        journal_dir,
        "unsafe.json",
        index=0,
        orders_sent=1,
        order_check_called=True,
        order_send_called=True,
    )

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    assert report["final_decision"] == "BLOCK"
    assert report["orders_sent"] == 0
    assert report["observed_orders_sent_sum"] == 1
    assert report["order_check_called"] is True
    assert report["order_send_called"] is True
    assert REASON_ORDERS_SENT_NONZERO in report["reason_codes"]
    assert REASON_ORDER_CHECK_CALLED in report["reason_codes"]
    assert REASON_ORDER_SEND_CALLED in report["reason_codes"]


def test_live_quality_report_handles_malformed_journals_safely(tmp_path):
    journal_dir = tmp_path / "journals"
    campaign_dir = tmp_path / "campaigns"
    historical_path = tmp_path / "historical.json"
    write_historical_report(historical_path, rate=0.02, signals=100, total=5_000)
    journal_dir.mkdir(parents=True)
    (journal_dir / "bad.json").write_text("{bad json", encoding="utf-8")

    report = analyze_live_sample_quality(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        historical_args=historical_args(historical_path, journal_dir),
        build_historical_if_missing=False,
    )

    assert report["final_decision"] == "WARN"
    assert report["malformed_journals"] == 1
    assert REASON_MALFORMED_LIVE_JOURNALS in report["reason_codes"]


def historical_args(historical_path: Path, journal_dir: Path) -> argparse.Namespace:
    return argparse.Namespace(
        historical_report=str(historical_path),
        journal_dir=str(journal_dir),
        tolerance_z=3.0,
    )


def write_historical_report(path: Path, *, rate: float, signals: int, total: int) -> None:
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "historical_signal_replay",
        "total_observations": total,
        "total_bars_replayed": total,
        "signal_count": signals,
        "buy_signal_count": signals // 2,
        "sell_signal_count": signals - (signals // 2),
        "actionable_signal_rate": rate,
        "diagnostics": {"average_bars_between_signals": 31.0},
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_campaign(campaign_dir: Path, campaign_id: str, *, duplicate_bar_skipped: int = 0) -> None:
    campaign_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "dry_observation_campaign",
        "campaign_id": campaign_id,
        "started_at_utc": "2026-05-29T00:00:00+00:00",
        "ended_at_utc": "2026-05-29T01:00:00+00:00",
        "total_poll_iterations": 10,
        "duplicate_bar_skipped": duplicate_bar_skipped,
        "orders_sent": 0,
    }
    (campaign_dir / f"{campaign_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def write_journal(
    journal_dir: Path,
    filename: str,
    *,
    index: int,
    campaign_id: str = "campaign-a",
    final_decision: str = "BLOCK",
    side: str = "HOLD",
    orders_sent: int = 0,
    order_check_called: bool = False,
    order_send_called: bool = False,
    reason_codes: list[str] | None = None,
    reasons: list[str] | None = None,
    diagnostics: dict | None = None,
) -> None:
    journal_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime(2026, 5, 29, tzinfo=timezone.utc) + timedelta(minutes=15 * index)
    codes = [] if final_decision == "SIGNAL" else (reason_codes or ["NO_ACTIONABLE_SIGNAL"])
    payload = {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "campaign_id": campaign_id,
        "timestamp_utc": timestamp.isoformat(),
        "final_decision": final_decision,
        "reason_codes": codes,
        "reasons": [] if final_decision == "SIGNAL" else (reasons or [f"{code}: no crossover" for code in codes]),
        "orders_sent": orders_sent,
        "order_check_called": order_check_called,
        "order_send_called": order_send_called,
        "symbol": {
            "name": "GOLD_",
            "point": 0.01,
            "trade_tick_size": 0.01,
            "trade_tick_value": 1.0,
            "volume_min": 0.01,
            "volume_step": 0.01,
            "volume_max": 50.0,
            "trade_stops_level": 0,
            "spread": 55,
        },
        "config": {"symbol": "GOLD_"},
        "timeframe": "M15",
        "latest_closed_bar_time": str(timestamp),
        "current_spread_points": 55.0,
        "risk_preview": risk_preview_payload(final_decision=final_decision, side=side, reason_codes=codes),
        "selected_parameters": {
            "fast_sma": 10,
            "slow_sma": 40,
            "atr_period": 14,
            "atr_stop_multiplier": 1.5,
            "reward_risk_ratio": 1.5,
        },
        "signal": signal_payload(side=side, final_decision=final_decision),
    }
    if diagnostics is not None:
        payload["diagnostics"] = diagnostics
    (journal_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def signal_payload(*, side: str, final_decision: str) -> dict:
    if side in {"BUY", "SELL"}:
        return {
            "symbol": "GOLD_",
            "side": side,
            "confidence": 0.55,
            "entry_price": 100.0,
            "stop_loss_price": 85.0 if side == "BUY" else 115.0,
            "take_profit_price": 122.5 if side == "BUY" else 77.5,
            "reason": "fast SMA crossed above slow SMA" if side == "BUY" else "fast SMA crossed below slow SMA",
        }
    return {
        "symbol": "GOLD_",
        "side": side,
        "confidence": 0.0,
        "entry_price": 100.0,
        "stop_loss_price": None,
        "take_profit_price": None,
        "reason": "no crossover" if final_decision != "SIGNAL" else "",
    }


def risk_preview_payload(*, final_decision: str, side: str, reason_codes: list[str]) -> dict:
    is_candidate = side in {"BUY", "SELL"}
    if "LOT_BELOW_VOLUME_MIN" in reason_codes:
        return {
            "evaluated": True,
            "allowed": False,
            "volume": 0.0,
            "reason_codes": reason_codes,
            "reasons": ["LOT_BELOW_VOLUME_MIN: calculated volume below broker minimum"],
            "risk_amount": 2.5,
            "risk_per_lot": 1250.0,
            "stop_distance_points": 1000.0,
            "take_profit_distance_points": 1500.0,
            "lot_below_minimum": True,
            "spread_filter": {
                "current_spread_points": 55.0,
                "max_spread_points": 350.0,
                "allowed": True,
            },
        }
    return {
        "evaluated": is_candidate,
        "allowed": final_decision == "SIGNAL",
        "volume": 0.01 if final_decision == "SIGNAL" else 0.0,
        "reason_codes": [] if final_decision == "SIGNAL" else ([] if not is_candidate else reason_codes),
        "reasons": [],
        "risk_amount": 2.5 if is_candidate else 0.0,
        "risk_per_lot": 100.0 if is_candidate else 0.0,
        "stop_distance_points": 100.0 if is_candidate else None,
        "take_profit_distance_points": 150.0 if is_candidate else None,
        "lot_below_minimum": False,
        "spread_filter": {
            "current_spread_points": 55.0,
            "max_spread_points": 350.0,
            "allowed": True,
        },
    }


def diagnostics_payload() -> dict:
    return {
        "schema_version": 1,
        "failed_pre_signal_rule_names": [],
        "failed_feasibility_rule_names": ["LOT_BELOW_VOLUME_MIN"],
        "signal": {
            "fast_sma": 101.5,
            "slow_sma": 100.5,
            "previous_fast_sma": 99.0,
            "previous_slow_sma": 100.0,
            "sma_crossover_state": "CROSSED_UP",
            "atr": 8.5,
            "stop_distance": 15.0,
            "stop_distance_points": 1500.0,
            "failed_pre_signal_rule_names": [],
        },
        "feasibility": {
            "computed_lot": 0.0019,
            "normalized_lot": 0.0,
            "broker_volume_min": 0.01,
            "broker_volume_step": 0.01,
            "broker_volume_max": 50.0,
            "spread_points": 55.0,
            "max_allowed_spread_points": 350.0,
            "spread_allowed": True,
            "stop_distance_points": 1500.0,
            "take_profit_distance_points": 2250.0,
            "risk_amount": 2.5,
            "risk_per_lot": 1250.0,
            "failed_feasibility_rule_names": ["LOT_BELOW_VOLUME_MIN"],
        },
    }
