from __future__ import annotations

import pandas as pd

from scripts.backtest_baseline_report import REASON_NO_BACKTEST_DATA
from scripts.backtest_parameter_stability_report import (
    WARNING_BEST_PARAM_ISOLATED,
    WARNING_MEDIAN_PARAM_WEAK,
    WARNING_STRESS_TEST_FRAGILE,
    StabilityThresholds,
    build_stability_diagnostics,
    run_parameter_stability_report,
)
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import RiskConfig


SYMBOL_INFO = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
    "spread": 0,
}

PARAMETER_VALUES = {
    "fast_sma": [10, 20],
    "slow_sma": [40, 50],
    "atr_stop_multiplier": [1.0, 1.5],
    "reward_risk_ratio": [1.0, 1.5],
}


def test_isolated_best_parameter_detection():
    rows = [
        parameter_row(20, 50, 1.5, 1.5, net_profit=100.0, profit_factor=1.8, robustness_score=0.95),
        parameter_row(10, 50, 1.5, 1.5, net_profit=10.0, profit_factor=1.05, robustness_score=0.40),
        parameter_row(20, 40, 1.5, 1.5, net_profit=12.0, profit_factor=1.05, robustness_score=0.41),
        parameter_row(20, 50, 1.0, 1.5, net_profit=8.0, profit_factor=1.01, robustness_score=0.39),
        parameter_row(20, 50, 1.5, 1.0, net_profit=7.0, profit_factor=1.01, robustness_score=0.38),
    ]

    diagnostics = build_stability_diagnostics(
        rows=rows,
        parameter_values=PARAMETER_VALUES,
        thresholds=StabilityThresholds(neighbor_net_profit_ratio=0.35),
    )

    assert WARNING_BEST_PARAM_ISOLATED in diagnostics["warning_flags"]


def test_median_parameter_weakness_detection():
    rows = [
        parameter_row(20, 50, 1.5, 1.5, net_profit=50.0, profit_factor=1.4, robustness_score=0.90),
        parameter_row(10, 40, 1.0, 1.0, net_profit=-15.0, profit_factor=0.8, robustness_score=0.20),
        parameter_row(10, 50, 1.0, 1.5, net_profit=-20.0, profit_factor=0.7, robustness_score=0.15),
    ]

    diagnostics = build_stability_diagnostics(
        rows=rows,
        parameter_values=PARAMETER_VALUES,
        thresholds=StabilityThresholds(min_median_profit_factor=1.0),
    )

    assert WARNING_MEDIAN_PARAM_WEAK in diagnostics["warning_flags"]


def test_stress_fragility_detection():
    rows = [
        parameter_row(20, 50, 1.5, 1.5, stress_survived=True),
        parameter_row(10, 50, 1.5, 1.5, stress_survived=False),
        parameter_row(20, 40, 1.5, 1.5, stress_survived=False),
        parameter_row(20, 50, 1.0, 1.5, stress_survived=False),
    ]

    diagnostics = build_stability_diagnostics(
        rows=rows,
        parameter_values=PARAMETER_VALUES,
        thresholds=StabilityThresholds(min_stress_survival_pct=0.50),
    )

    assert WARNING_STRESS_TEST_FRAGILE in diagnostics["warning_flags"]


def test_empty_data_handling():
    empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"])

    report = run_parameter_stability_report(
        bars=empty,
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        data_source={"kind": "test"},
        initial_balance=10_000.0,
        risk_config=RiskConfig(risk_per_trade_pct=1.0, max_spread_points=1_000.0),
        parameter_grid=[BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2)],
        parameter_values={
            "fast_sma": [2],
            "slow_sma": [3],
            "atr_stop_multiplier": [1.5],
            "reward_risk_ratio": [1.5],
        },
        spread_multipliers=[1.0],
        slippage_points=[0.0],
        thresholds=StabilityThresholds(),
    )

    assert report["status"] == "NO_DATA"
    assert report["reason_codes"] == [REASON_NO_BACKTEST_DATA]
    assert report["orders_sent"] == 0


def test_orders_sent_always_zero():
    report = run_parameter_stability_report(
        bars=make_bars([10, 9, 8, 7, 6, 7, 8, 9, 8, 7, 8, 9]),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        data_source={"kind": "test"},
        initial_balance=10_000.0,
        risk_config=RiskConfig(risk_per_trade_pct=1.0, max_spread_points=1_000.0),
        parameter_grid=[BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2)],
        parameter_values={
            "fast_sma": [2],
            "slow_sma": [3],
            "atr_stop_multiplier": [1.5],
            "reward_risk_ratio": [1.5],
        },
        spread_multipliers=[1.0],
        slippage_points=[0.0],
        thresholds=StabilityThresholds(),
    )

    assert report["orders_sent"] == 0
    assert all(row["orders_sent"] == 0 for row in report["parameter_results"])
    assert report["strategy_constraints"]["ai_model_trading"] is False
    assert report["strategy_constraints"]["martingale"] is False
    assert report["strategy_constraints"]["grid"] is False
    assert report["strategy_constraints"]["lot_increase_after_loss"] is False


def parameter_row(
    fast_sma: int,
    slow_sma: int,
    atr_stop_multiplier: float,
    reward_risk_ratio: float,
    *,
    net_profit: float = 25.0,
    profit_factor: float = 1.2,
    robustness_score: float = 0.5,
    stress_survived: bool = True,
) -> dict:
    return {
        "parameters": {
            "fast_sma": fast_sma,
            "slow_sma": slow_sma,
            "atr_period": 14,
            "atr_stop_multiplier": atr_stop_multiplier,
            "reward_risk_ratio": reward_risk_ratio,
        },
        "total_trades": 10,
        "win_rate": 0.5,
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        "max_drawdown": 20.0,
        "max_drawdown_pct": 0.002,
        "average_r": 0.1,
        "max_consecutive_losses": 2,
        "robustness_score": robustness_score,
        "stress_survived": stress_survived,
        "stress_survival_rate": 1.0 if stress_survived else 0.0,
        "profit_concentration": {
            "top_trade_count": 3,
            "gross_profit": 100.0,
            "top_trade_profit": 20.0,
            "top_trade_profit_share": 0.20,
        },
        "orders_sent": 0,
    }


def make_bars(closes: list[float]) -> pd.DataFrame:
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * index),
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "spread": 0.0,
            }
        )
    return pd.DataFrame(rows)
