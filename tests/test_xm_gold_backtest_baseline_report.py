from __future__ import annotations

import pandas as pd

from scripts.backtest_baseline_report import (
    BacktestConfig,
    REASON_NO_BACKTEST_DATA,
    calculate_metrics,
    max_drawdown,
    run_backtest_report,
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


def make_bars(closes: list[float], *, spread: float = 0.0, range_size: float = 0.2) -> pd.DataFrame:
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * index),
                "open": close,
                "high": close + range_size,
                "low": close - range_size,
                "close": close,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)


def test_no_lookahead_bias_entries_use_next_bar_after_signal():
    closes = [10, 9, 8, 7, 6, 7, 8, 9, 9, 9]
    report = run_test_backtest(closes, spread_points=0.0)

    assert report["metrics"]["total_trades"] >= 1
    first_trade = report["trades"][0]
    assert first_trade["entry_bar_index"] == first_trade["signal_bar_index"] + 1
    assert first_trade["entry_time"] > first_trade["signal_time"]


def test_one_position_only_prevents_overlapping_trades():
    closes = [10, 9, 8, 7, 6, 7, 8, 7, 6, 7, 8, 7, 6, 7, 8]
    report = run_test_backtest(
        closes,
        spread_points=0.0,
        atr_stop_multiplier=5.0,
        reward_risk_ratio=100.0,
    )
    trades = report["trades"]

    assert trades
    for previous, current in zip(trades, trades[1:]):
        assert current["entry_bar_index"] > previous["exit_bar_index"]


def test_spread_cost_is_applied_to_trade_pnl():
    closes = [10, 9, 8, 7, 6, 7, 8, 9, 9, 9]
    no_spread = run_test_backtest(closes, spread_points=0.0)
    with_spread = run_test_backtest(closes, spread_points=10.0)

    assert no_spread["metrics"]["total_trades"] == with_spread["metrics"]["total_trades"]
    assert with_spread["trades"][0]["spread_cost"] > 0
    assert with_spread["metrics"]["net_profit"] < no_spread["metrics"]["net_profit"]


def test_drawdown_calculation():
    assert max_drawdown([100.0, 125.0, 90.0, 110.0, 80.0]) == 45.0

    metrics = calculate_metrics(
        trades=[],
        initial_balance=100.0,
        ending_balance=80.0,
        equity_curve=[100.0, 125.0, 90.0, 110.0, 80.0],
        daily_pnl={},
    )
    assert metrics["max_drawdown"] == 45.0


def test_empty_data_handling():
    empty = pd.DataFrame(columns=["time", "open", "high", "low", "close"])
    report = run_test_backtest_from_frame(empty)

    assert report["status"] == "NO_DATA"
    assert report["reason_codes"] == [REASON_NO_BACKTEST_DATA]
    assert report["metrics"]["total_trades"] == 0


def run_test_backtest(
    closes: list[float],
    *,
    spread_points: float,
    atr_stop_multiplier: float = 1.0,
    reward_risk_ratio: float = 1.5,
) -> dict:
    return run_test_backtest_from_frame(
        make_bars(closes, spread=spread_points),
        spread_points=spread_points,
        atr_stop_multiplier=atr_stop_multiplier,
        reward_risk_ratio=reward_risk_ratio,
    )


def run_test_backtest_from_frame(
    bars: pd.DataFrame,
    *,
    spread_points: float = 0.0,
    atr_stop_multiplier: float = 1.0,
    reward_risk_ratio: float = 1.5,
) -> dict:
    return run_backtest_report(
        bars=bars,
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        config=BacktestConfig(
            signal=BaselineSignalConfig(
                fast_sma=2,
                slow_sma=3,
                atr_period=2,
                atr_stop_multiplier=atr_stop_multiplier,
                reward_risk_ratio=reward_risk_ratio,
            ),
            risk=RiskConfig(risk_per_trade_pct=1.0, max_spread_points=1_000.0),
            initial_balance=10_000.0,
            spread_points=spread_points,
        ),
        data_source={"kind": "test"},
    )
