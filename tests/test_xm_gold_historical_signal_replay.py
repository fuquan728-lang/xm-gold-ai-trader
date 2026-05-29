from __future__ import annotations

import pandas as pd

from scripts.historical_signal_replay import (
    REASON_NO_HISTORICAL_DATA,
    REASON_SIGNAL_SCARCITY,
    replay_observations,
    run_historical_signal_replay,
)
from src.strategy.baseline_signal import BaselineSignalConfig, TradeSignal


SYMBOL_INFO = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
    "spread": 20,
}


def test_no_lookahead_uses_only_bars_visible_at_each_closed_bar():
    bars = make_bars([10, 9, 8, 9, 10, 11])
    generator = SpyGenerator()

    observations = replay_observations(
        bars=bars,
        symbol="GOLD_",
        timeframe="M15",
        signal_config=make_signal_config(),
        symbol_info=SYMBOL_INFO,
        signal_generator=generator,
    )

    assert [length for length, _last_close in generator.calls] == [1, 2, 3, 4, 5, 6]
    assert [obs["bars_visible"] for obs in observations] == [1, 2, 3, 4, 5, 6]
    assert observations[-1]["latest_closed_bar_time"] == str(bars.iloc[-1]["time"])


def test_one_observation_per_bar():
    bars = make_bars([10, 9, 8, 9, 10, 11, 12, 11])

    report = run_historical_signal_replay(
        bars=bars,
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        signal_config=make_signal_config(),
        selected_parameters_source="test",
        include_observations=True,
    )

    assert report["total_bars_replayed"] == len(bars)
    assert report["total_observations"] == len(bars)
    assert len(report["observations"]) == len(bars)


def test_no_order_check_or_order_send():
    report = run_historical_signal_replay(
        bars=make_bars([10, 9, 8, 9, 10, 11, 12, 11]),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        signal_config=make_signal_config(),
        selected_parameters_source="test",
        include_observations=True,
    )

    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False
    assert all(obs["orders_sent"] == 0 for obs in report["observations"])
    assert all(obs["order_check_called"] is False for obs in report["observations"])
    assert all(obs["order_send_called"] is False for obs in report["observations"])


def test_signal_scarcity_detection():
    report = run_historical_signal_replay(
        bars=make_bars([10.0] * 20),
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        signal_config=make_signal_config(),
        selected_parameters_source="test",
    )

    assert report["signal_count"] == 0
    assert report["diagnostics"]["signal_scarcity_detected"] is True
    assert report["diagnostics"]["longest_no_signal_streak"] == 20
    assert REASON_SIGNAL_SCARCITY in report["reason_codes"]


def test_empty_data_handling():
    empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "spread"])

    report = run_historical_signal_replay(
        bars=empty,
        symbol="GOLD_",
        timeframe="M15",
        symbol_info=SYMBOL_INFO,
        signal_config=make_signal_config(),
        selected_parameters_source="test",
        include_observations=True,
    )

    assert report["status"] == "NO_DATA"
    assert report["reason_codes"] == [REASON_NO_HISTORICAL_DATA]
    assert report["total_observations"] == 0
    assert report["observations"] == []
    assert report["orders_sent"] == 0


class SpyGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[int, float]] = []

    def generate(self, bars: pd.DataFrame, symbol: str) -> TradeSignal:
        self.calls.append((len(bars), float(bars.iloc[-1]["close"])))
        return TradeSignal(symbol=symbol, side="HOLD", confidence=0.0, reason="spy hold")


def make_signal_config() -> BaselineSignalConfig:
    return BaselineSignalConfig(
        fast_sma=2,
        slow_sma=3,
        atr_period=2,
        atr_stop_multiplier=1.5,
        reward_risk_ratio=1.5,
    )


def make_bars(closes: list[float], *, spread: float = 20.0) -> pd.DataFrame:
    rows = []
    for index, close in enumerate(closes):
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * index),
                "open": close,
                "high": close + 0.2,
                "low": close - 0.2,
                "close": close,
                "spread": spread,
            }
        )
    return pd.DataFrame(rows)
