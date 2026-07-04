import math

import pandas as pd

from scripts.strategy_four_pack_report import (
    build_four_pack_report,
    calculate_r_metrics,
    decide_strategy_status,
)


def test_four_pack_report_is_read_only_and_covers_requested_families():
    report = build_four_pack_report(
        synthetic_m15_bars(1200),
        symbol="GOLD_",
        source_path="unit_test",
        min_trades=1,
    )

    families = {row["family"] for row in report["strategies"]}

    assert report["mode"] == "strategy_four_pack_report"
    assert report["hypothetical_only"] is True
    assert report["no_spread_cost_mode"] is True
    assert report["production_strategy_unchanged"] is True
    assert report["orders_sent"] == 0
    assert "M15" in report["current_level_snapshot"]
    assert report["current_level_snapshot"]["M15"]["support"] is not None
    assert report["current_level_snapshot"]["M15"]["resistance"] is not None
    assert report["current_level_snapshot"]["M15"]["entry_exit_plans"]
    assert report["current_level_snapshot"]["M15"]["reference_levels"]["rolling_32"]["support"] is not None
    assert "nearest_support" in report["current_level_snapshot"]["M15"]["nearest_reference_levels"]
    first_plan = report["current_level_snapshot"]["M15"]["entry_exit_plans"][0]
    assert first_plan["confirmation_required"]
    assert first_plan["take_profit_1r"] is not None
    assert first_plan["move_stop_to_breakeven_at"] is not None
    assert first_plan["max_hold_bars"] > 0
    assert first_plan["confluence_score"] > 0
    assert families == {"trend_following", "breakout", "pullback_continuation", "mean_reversion"}
    assert len(report["strategies"]) == 5
    assert len(report["ranking"]) == 5

    sample = next((trade for row in report["strategies"] for trade in row["sample_trades"]), None)
    if sample is not None:
        assert "support_level" in sample
        assert "resistance_level" in sample
        assert sample["entry_trigger"]
        assert sample["exit_plan"]
        assert sample["level_source"]
        assert sample["confirmation_checklist"]
        assert sample["confluence_score"] > 0
        assert sample["management_plan"]["partial_take_profit_at_1r"] is not None
        assert sample["management_plan"]["move_stop_to_breakeven_at"] is not None
        assert sample["management_plan"]["time_stop_bars"] > 0


def test_positive_oos_metrics_can_be_marked_research_candidate():
    metrics = calculate_r_metrics(
        [
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
        ]
    )
    train_metrics = calculate_r_metrics(
        [
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
        ]
    )
    test_metrics = calculate_r_metrics(
        [
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
            {"r_multiple": -1.0, "side": "SELL"},
            {"r_multiple": 2.0, "side": "BUY"},
        ]
    )

    status, reason = decide_strategy_status(metrics, train_metrics, test_metrics)

    assert status == "RESEARCH_CANDIDATE"
    assert "out-of-sample" in reason


def test_train_only_edge_is_marked_overfit_risk():
    metrics = calculate_r_metrics(
        [{"r_multiple": 2.0, "side": "BUY"}, {"r_multiple": -1.0, "side": "SELL"}] * 6
    )
    train_metrics = calculate_r_metrics([{"r_multiple": 2.0, "side": "BUY"}] * 6)
    test_metrics = calculate_r_metrics([{"r_multiple": -1.0, "side": "SELL"}] * 6)

    status, reason = decide_strategy_status(metrics, train_metrics, test_metrics)

    assert status == "OVERFIT_RISK"
    assert "out-of-sample" in reason


def synthetic_m15_bars(count: int) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=count, freq="15min", tz="UTC")
    closes = [
        5000.0 + index * 0.2 + math.sin(index / 12.0) * 10.0 + math.sin(index / 3.0) * 2.0
        for index in range(count)
    ]
    opens = [closes[0], *closes[:-1]]
    highs = [max(open_price, close) + 3.0 for open_price, close in zip(opens, closes)]
    lows = [min(open_price, close) - 3.0 for open_price, close in zip(opens, closes)]
    return pd.DataFrame(
        {
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [1000] * count,
            "spread": [55] * count,
            "real_volume": [0] * count,
        }
    )
