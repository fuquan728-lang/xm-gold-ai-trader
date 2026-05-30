from __future__ import annotations

import pandas as pd

from scripts.strategy_hypothesis_lab import (
    MODE,
    PROJECT,
    REASON_NO_HISTORICAL_DATA,
    REASON_SYMBOL_INFO_UNAVAILABLE,
    HypothesisDefinition,
    run_strategy_hypothesis_lab,
)
from src.broker.order_executor import TradingConfig
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import REASON_LOT_BELOW_VOLUME_MIN, RiskConfig


SYMBOL_INFO = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "volume_min": 0.01,
    "volume_step": 0.01,
    "volume_max": 50.0,
    "trade_stops_level": 0,
    "spread": 55,
}


def test_hypothesis_lab_is_read_only_and_reports_required_fields():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    assert report["project"] == PROJECT
    assert report["mode"] == MODE
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False
    assert report["hypothetical_only"] is True
    assert report["production_strategy_unchanged"] is True
    assert report["ai_annotation_read_only"] is True
    row = report["hypotheses"][0]
    assert row["candidate_signal_count"] > 0
    assert row["final_theoretical_signal_count"] == 0
    assert row["estimated_min_lot_feasibility_issues"] > 0


def test_candidate_only_diagnostic_does_not_apply_risk_gate_to_final_count():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            risk_gated_crossover("risk_gated"),
            candidate_only_crossover("candidate_only"),
        ],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    risk_gated, candidate_only = report["hypotheses"]

    assert risk_gated["candidate_signal_count"] == candidate_only["candidate_signal_count"]
    assert risk_gated["final_theoretical_signal_count"] == 0
    assert candidate_only["final_theoretical_signal_count"] == candidate_only["candidate_signal_count"]
    assert REASON_LOT_BELOW_VOLUME_MIN in risk_gated["block_reason_counts"]
    assert candidate_only["estimated_min_lot_feasibility_issues"] == risk_gated["estimated_min_lot_feasibility_issues"]


def test_minimum_lot_feasibility_study_reports_distributions_and_required_budget():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=10.0,
        data_source={"kind": "unit_test"},
    )

    row = report["hypotheses"][0]
    study = row["minimum_lot_feasibility"]

    assert report["minimum_lot_feasibility_study"] == study
    assert study["hypothetical_only"] is True
    assert study["not_production_settings"] is True
    assert study["candidate_count"] == row["candidate_signal_count"]
    assert study["volume_min"] == 0.01
    assert study["volume_step"] == 0.01
    assert study["lot_below_volume_min_count"] == row["candidate_signal_count"]
    assert study["computed_lot_distribution"]["count"] == row["candidate_signal_count"]
    assert study["computed_lot_distribution"]["max"] < study["volume_min"]
    assert study["normalized_lot_distribution"]["max"] == 0.0
    assert study["risk_per_lot_distribution"]["min"] > 0
    assert study["stop_distance_points_distribution"]["min"] > 0
    assert study["atr_price_distribution"]["min"] > 0
    assert study["risk_shortfall_to_min_lot_distribution"]["min"] > 0
    assert study["account_balance_required_at_current_risk_pct_distribution"]["min"] > 10.0
    assert study["risk_pct_required_at_account_equity_distribution"]["min"] > 0.25

    scenarios = {scenario["name"]: scenario for scenario in study["hypothetical_risk_budget_scenarios"]}
    assert scenarios["current_config"]["feasible_candidate_count"] == 0
    assert scenarios["all_candidates_requirement"]["feasible_candidate_count"] == row["candidate_signal_count"]


def test_minimum_lot_feasibility_scenarios_can_be_feasible_without_order_paths():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[risk_gated_crossover("risk_gated")],
        account_equity=100_000.0,
        data_source={"kind": "unit_test"},
    )

    row = report["hypotheses"][0]
    study = row["minimum_lot_feasibility"]
    scenarios = {scenario["name"]: scenario for scenario in study["hypothetical_risk_budget_scenarios"]}

    assert row["candidate_signal_count"] > 0
    assert row["final_theoretical_signal_count"] == row["candidate_signal_count"]
    assert study["lot_below_volume_min_count"] == 0
    assert study["normalized_lot_distribution"]["max"] >= study["volume_min"]
    assert scenarios["current_config"]["hypothetical_only"] is True
    assert scenarios["current_config"]["feasible_candidate_count"] == row["candidate_signal_count"]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_trend_continuation_hypothesis_generates_candidates_without_changing_baseline():
    report = run_strategy_hypothesis_lab(
        bars=trending_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(risk=RiskConfig(max_spread_points=350)),
        hypotheses=[
            candidate_only_crossover("crossover"),
            HypothesisDefinition(
                name="trend_continuation",
                family="trend_continuation",
                description="Unit-test trend continuation diagnostic.",
                signal_mode="trend_continuation",
                signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=5, atr_period=2),
                risk_gated=False,
            ),
        ],
        account_equity=100_000.0,
        data_source={"kind": "unit_test"},
    )

    crossover, trend = report["hypotheses"]

    assert crossover["candidate_signal_count"] == 0
    assert trend["candidate_signal_count"] > 0
    assert trend["final_theoretical_signal_count"] == trend["candidate_signal_count"]
    assert report["production_strategy_unchanged"] is True


def test_empty_data_returns_warn_without_order_boundaries():
    report = run_strategy_hypothesis_lab(
        bars=pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"]),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        trading_config=TradingConfig(),
        hypotheses=[risk_gated_crossover("risk_gated")],
    )

    assert report["final_decision"] == "WARN"
    assert report["reason_codes"] == [REASON_NO_HISTORICAL_DATA]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_missing_symbol_info_returns_warn_without_order_boundaries():
    report = run_strategy_hypothesis_lab(
        bars=oscillating_bars(),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=None,
        trading_config=TradingConfig(),
        hypotheses=[risk_gated_crossover("risk_gated")],
    )

    assert report["final_decision"] == "WARN"
    assert report["reason_codes"] == [REASON_SYMBOL_INFO_UNAVAILABLE]
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def risk_gated_crossover(name: str) -> HypothesisDefinition:
    return HypothesisDefinition(
        name=name,
        family="unit_test",
        description="Unit-test risk-gated SMA crossover.",
        signal_mode="sma_crossover",
        signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2),
        risk_gated=True,
    )


def candidate_only_crossover(name: str) -> HypothesisDefinition:
    return HypothesisDefinition(
        name=name,
        family="unit_test",
        description="Unit-test candidate-only SMA crossover.",
        signal_mode="sma_crossover",
        signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2),
        risk_gated=False,
    )


def oscillating_bars() -> pd.DataFrame:
    closes = [10, 9, 8, 9, 10, 11, 10, 9, 8, 9, 10, 11, 10, 9, 8, 9, 10, 11]
    return bars_from_closes(closes)


def trending_bars() -> pd.DataFrame:
    return bars_from_closes(list(range(10, 40)))


def bars_from_closes(closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": [f"2026-05-29T{i:02d}:00:00+00:00" for i in range(len(closes))],
            "open": closes,
            "high": [close + 0.3 for close in closes],
            "low": [close - 0.3 for close in closes],
            "close": closes,
            "spread": [55 for _ in closes],
        }
    )
