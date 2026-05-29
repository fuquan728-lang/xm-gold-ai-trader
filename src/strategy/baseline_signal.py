from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd


SignalSide = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True, slots=True)
class TradeSignal:
    symbol: str
    side: SignalSide
    confidence: float
    entry_price: float | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    reason: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.side in {"BUY", "SELL"} and self.entry_price is not None and self.stop_loss_price is not None


@dataclass(frozen=True, slots=True)
class BaselineSignalConfig:
    fast_sma: int = 20
    slow_sma: int = 50
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    reward_risk_ratio: float = 1.5

    def __post_init__(self) -> None:
        if self.fast_sma <= 1:
            raise ValueError("fast_sma must be > 1")
        if self.slow_sma <= self.fast_sma:
            raise ValueError("slow_sma must be greater than fast_sma")
        if self.atr_period <= 1:
            raise ValueError("atr_period must be > 1")
        if self.atr_stop_multiplier <= 0:
            raise ValueError("atr_stop_multiplier must be positive")
        if self.reward_risk_ratio <= 0:
            raise ValueError("reward_risk_ratio must be positive")


class BaselineSignalGenerator:
    """Small, reproducible SMA crossover baseline.

    This module produces only direction and price levels. Position size and
    execution permission stay in RiskManager and OrderExecutor.
    """

    def __init__(self, config: BaselineSignalConfig | None = None) -> None:
        self.config = config or BaselineSignalConfig()

    def generate(self, bars: "pd.DataFrame", symbol: str) -> TradeSignal:
        required = {"high", "low", "close"}
        missing = required.difference(bars.columns)
        if missing:
            raise ValueError(f"bars are missing required columns: {sorted(missing)}")

        minimum_bars = max(self.config.slow_sma, self.config.atr_period) + 2
        if len(bars) < minimum_bars:
            return TradeSignal(symbol=symbol, side="HOLD", confidence=0.0, reason="not enough bars")

        frame = bars.copy()
        frame["fast_sma"] = frame["close"].rolling(self.config.fast_sma).mean()
        frame["slow_sma"] = frame["close"].rolling(self.config.slow_sma).mean()
        frame["atr"] = _average_true_range(frame, self.config.atr_period)

        previous = frame.iloc[-2]
        latest = frame.iloc[-1]
        if _is_nan(previous["fast_sma"], previous["slow_sma"], latest["fast_sma"], latest["slow_sma"], latest["atr"]):
            return TradeSignal(symbol=symbol, side="HOLD", confidence=0.0, reason="indicator warmup")

        crossed_up = previous["fast_sma"] <= previous["slow_sma"] and latest["fast_sma"] > latest["slow_sma"]
        crossed_down = previous["fast_sma"] >= previous["slow_sma"] and latest["fast_sma"] < latest["slow_sma"]
        entry = float(latest["close"])
        stop_distance = float(latest["atr"]) * self.config.atr_stop_multiplier

        if crossed_up:
            stop = entry - stop_distance
            take_profit = entry + (stop_distance * self.config.reward_risk_ratio)
            return TradeSignal(
                symbol=symbol,
                side="BUY",
                confidence=0.55,
                entry_price=entry,
                stop_loss_price=stop,
                take_profit_price=take_profit,
                reason="fast SMA crossed above slow SMA",
            )
        if crossed_down:
            stop = entry + stop_distance
            take_profit = entry - (stop_distance * self.config.reward_risk_ratio)
            return TradeSignal(
                symbol=symbol,
                side="SELL",
                confidence=0.55,
                entry_price=entry,
                stop_loss_price=stop,
                take_profit_price=take_profit,
                reason="fast SMA crossed below slow SMA",
            )

        return TradeSignal(symbol=symbol, side="HOLD", confidence=0.0, entry_price=entry, reason="no crossover")


def _average_true_range(frame: "pd.DataFrame", period: int) -> "pd.Series":
    previous_close = frame["close"].shift(1)
    true_range = frame[["high", "low"]].assign(
        high_close=(frame["high"] - previous_close).abs(),
        low_close=(frame["low"] - previous_close).abs(),
        high_low=frame["high"] - frame["low"],
    )[["high_close", "low_close", "high_low"]].max(axis=1)
    return true_range.rolling(period).mean()


def _is_nan(*values: object) -> bool:
    return any(value != value for value in values)

