from __future__ import annotations

import pandas as pd

from scripts.backtest_walk_forward_report import (
    GateConfig,
    REASON_MAX_DRAWDOWN_FAILED,
    REASON_MIN_TRADES_PER_FOLD_FAILED,
    REASON_NO_BACKTEST_DATA,
    REASON_SINGLE_FOLD_PROFIT_DOMINANCE,
    REASON_STRESS_PROFIT_FACTOR_FAILED,
    apply_spread_slippage,
    evaluate_gates,
    make_walk_forward_folds,
    run_walk_forward_report,
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
    "spread": 10,
}


def test_no_lookahead_in_walk_forward_split():
    folds = make_walk_forward_folds(
        total_bars=120,
        train_bars=50,
        validation_bars=20,
        test_bars=10,
        step_bars=10,
    )

    assert folds
    for fold in folds:
        assert fold.train_start < fold.train_end
        assert fold.train_end == fold.validation_start
        assert fold.validation_end == fold.test_start
        assert fold.test_start >= fold.validation_end


def test_folds_do_not_overlap_in_test_windows_when_step_equals_test_size():
    folds = make_walk_forward_folds(
        total_bars=120,
        train_bars=50,
        validation_bars=20,
        test_bars=10,
        step_bars=10,
    )

    for previous, current in zip(folds, folds[1:]):
        assert previous.test_end <= current.test_start


def test_robustness_matrix_applies_spread_and_slippage():
    bars = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="15min", tz="UTC"),
            "open": [1.0, 1.0],
            "high": [1.1, 1.1],
            "low": [0.9, 0.9],
            "close": [1.0, 1.0],
            "spread": [10.0, 20.0],
        }
    )

    stressed = apply_spread_slippage(
        bars=bars,
        symbol_info=SYMBOL_INFO,
        spread_multiplier=1.5,
        slippage_points=5.0,
    )

    assert list(stressed["spread"]) == [20.0, 35.0]


def test_pass_fail_gates_fail_weak_strategies():
    folds = [
        fold_metrics(fold_id=1, total_trades=1, net_profit=100.0, profit_factor=1.2, max_drawdown_pct=0.02),
        fold_metrics(fold_id=2, total_trades=10, net_profit=0.0, profit_factor=1.0, max_drawdown_pct=0.15),
    ]
    robustness = [
        {
            "total_trades": 5,
            "profit_factor": 0.5,
            "max_drawdown_pct": 0.03,
        }
    ]

    result = evaluate_gates(
        folds=folds,
        robustness_matrix=robustness,
        gates=GateConfig(
            min_trades_per_fold=5,
            max_single_fold_profit_share=0.75,
            min_stress_profit_factor=0.75,
            max_drawdown_pct=0.10,
        ),
    )

    codes = {failure["reason_code"] for failure in result["failures"]}
    assert result["passed"] is False
    assert REASON_MIN_TRADES_PER_FOLD_FAILED in codes
    assert REASON_SINGLE_FOLD_PROFIT_DOMINANCE in codes
    assert REASON_STRESS_PROFIT_FACTOR_FAILED in codes
    assert REASON_MAX_DRAWDOWN_FAILED in codes


def test_empty_data_handling():
    empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"])

    report = run_walk_forward_report(
        bars=empty,
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        data_source={"kind": "test"},
        train_bars=10,
        validation_bars=5,
        test_bars=5,
        step_bars=5,
        initial_balance=10_000.0,
        risk_config=RiskConfig(risk_per_trade_pct=1.0, max_spread_points=1_000.0),
        default_signal_config=BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2),
        parameter_grid=[BaselineSignalConfig(fast_sma=2, slow_sma=3, atr_period=2)],
        spread_multipliers=[1.0],
        slippage_points=[0.0],
        gates=GateConfig(),
    )

    assert report["status"] == "NO_DATA"
    assert report["reason_codes"] == [REASON_NO_BACKTEST_DATA]
    assert report["orders_sent"] == 0


def fold_metrics(
    *,
    fold_id: int,
    total_trades: int,
    net_profit: float,
    profit_factor: float,
    max_drawdown_pct: float,
) -> dict:
    return {
        "fold_id": fold_id,
        "total_trades": total_trades,
        "win_rate": 0.5,
        "net_profit": net_profit,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown_pct * 10_000,
        "max_drawdown_pct": max_drawdown_pct,
        "average_r": 0.0,
        "max_consecutive_losses": 1,
    }
