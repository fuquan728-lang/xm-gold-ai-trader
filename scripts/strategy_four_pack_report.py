from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PROJECT = "xm-gold-ai-trader"
MODE = "strategy_four_pack_report"
CAMPAIGN_VERSION = "v0.26.2"


@dataclass(frozen=True)
class TradeSetup:
    strategy: str
    family: str
    side: str
    signal_index: int
    entry_index: int
    entry_price: float
    stop_loss: float
    take_profit: float
    stop_distance: float
    reward_risk: float
    max_hold_bars: int
    reason: str
    support_level: float | None = None
    resistance_level: float | None = None
    level_source: str = ""
    entry_trigger: str = ""
    exit_plan: str = ""
    confirmation_checklist: tuple[str, ...] = ()
    confluence_score: int = 0
    confluence_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    timeframe: str
    description: str
    generator: Callable[[Any, int, str], TradeSetup | None]


def main() -> int:
    args = parse_args()
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for strategy four-pack research. Install requirements.txt.") from exc

    bars_m15 = load_bars(Path(args.input), pd)
    report = build_four_pack_report(
        bars_m15,
        symbol=args.symbol,
        source_path=str(args.input),
        initial_timeframe=args.timeframe,
        train_fraction=args.train_fraction,
        min_trades=args.min_trades,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def build_four_pack_report(
    bars_m15: Any,
    *,
    symbol: str = "GOLD_",
    source_path: str = "data/gold_m15.csv",
    initial_timeframe: str = "M15",
    train_fraction: float = 0.7,
    min_trades: int = 20,
) -> dict[str, Any]:
    prepared = prepare_timeframes(bars_m15)
    specs = build_strategy_specs()
    rows = []
    for spec in specs:
        frame = prepared[spec.timeframe]
        rows.append(evaluate_strategy(spec, frame, symbol=symbol, train_fraction=train_fraction))

    status, reason = decide_report_status(rows, min_trades=min_trades)
    return {
        "project": PROJECT,
        "mode": MODE,
        "campaign_version": CAMPAIGN_VERSION,
        "status": status,
        "reason": reason,
        "hypothetical_only": True,
        "no_spread_cost_mode": True,
        "production_strategy_unchanged": True,
        "orders_sent": 0,
        "symbol": symbol,
        "source_path": source_path,
        "initial_timeframe": initial_timeframe,
        "train_fraction": train_fraction,
        "min_trades_gate": min_trades,
        "bars": {timeframe: int(len(frame)) for timeframe, frame in prepared.items()},
        "current_level_snapshot": current_level_snapshot(prepared),
        "strategies": rows,
        "ranking": rank_strategies(rows),
        "next_actions": next_actions(rows),
    }


def build_strategy_specs() -> list[StrategySpec]:
    return [
        StrategySpec(
            name="h1_trend_follow_ema50_200_pullback",
            family="trend_following",
            timeframe="H1",
            description="EMA50/EMA200 trend direction with EMA50 pullback continuation on H1.",
            generator=trend_follow_setup,
        ),
        StrategySpec(
            name="h4_trend_follow_ema50_200_pullback",
            family="trend_following",
            timeframe="H4",
            description="EMA50/EMA200 trend direction with EMA50 pullback continuation on H4.",
            generator=trend_follow_setup,
        ),
        StrategySpec(
            name="m15_london_ny_breakout_atr_filter",
            family="breakout",
            timeframe="M15",
            description="London/New York rolling range breakout with ATR expansion filter.",
            generator=breakout_setup,
        ),
        StrategySpec(
            name="m15_h1_pullback_continuation_rsi_macd",
            family="pullback_continuation",
            timeframe="M15",
            description="H1 trend direction with M15 RSI pullback recovery and MACD momentum.",
            generator=pullback_continuation_setup,
        ),
        StrategySpec(
            name="m15_low_volatility_mean_reversion",
            family="mean_reversion",
            timeframe="M15",
            description="Low-volatility support/resistance bounce; disabled during strong EMA trend.",
            generator=mean_reversion_setup,
        ),
    ]


def evaluate_strategy(
    spec: StrategySpec,
    frame: Any,
    *,
    symbol: str,
    train_fraction: float,
) -> dict[str, Any]:
    trades = simulate_trades(frame, spec, symbol=symbol)
    split_index = max(1, min(len(frame) - 1, int(len(frame) * train_fraction))) if len(frame) else 0
    train_trades = [trade for trade in trades if int(trade["entry_index"]) < split_index]
    test_trades = [trade for trade in trades if int(trade["entry_index"]) >= split_index]
    metrics = calculate_r_metrics(trades)
    train_metrics = calculate_r_metrics(train_trades)
    test_metrics = calculate_r_metrics(test_trades)
    status, reason = decide_strategy_status(metrics, train_metrics, test_metrics)
    return {
        "name": spec.name,
        "family": spec.family,
        "timeframe": spec.timeframe,
        "description": spec.description,
        "status": status,
        "reason": reason,
        "hypothetical_only": True,
        "no_spread_cost_mode": True,
        "trade_count": metrics["trade_count"],
        "metrics": metrics,
        "train_metrics": train_metrics,
        "test_metrics": test_metrics,
        "sample_trades": trades[:5],
    }


def simulate_trades(frame: Any, spec: StrategySpec, *, symbol: str) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    open_setup: TradeSetup | None = None
    start_index = 220 if spec.timeframe in {"H1", "H4"} else 80
    for index in range(start_index, len(frame)):
        bar = frame.iloc[index]
        if open_setup is not None:
            exit_price, exit_reason = exit_for_bar(open_setup, bar)
            if exit_price is None:
                bars_held = index - open_setup.entry_index
                if bars_held >= open_setup.max_hold_bars:
                    exit_price = float(bar["close"])
                    exit_reason = "time_stop"
                else:
                    continue
            trades.append(close_trade(open_setup, frame, index, exit_price, exit_reason))
            open_setup = None
            continue

        setup = spec.generator(frame, index, symbol)
        if setup is not None:
            open_setup = setup

    if open_setup is not None and len(frame) > 0:
        final_index = len(frame) - 1
        trades.append(close_trade(open_setup, frame, final_index, float(frame.iloc[final_index]["close"]), "end_of_data"))
    return trades


def trend_follow_setup(frame: Any, entry_index: int, symbol: str) -> TradeSetup | None:
    signal = frame.iloc[entry_index - 1]
    previous = frame.iloc[entry_index - 2]
    if has_nan(signal, ("ema50", "ema200", "atr", "rsi")) or has_nan(previous, ("ema50", "ema200")):
        return None
    atr = float(signal["atr"])
    if atr <= 0:
        return None
    entry = float(frame.iloc[entry_index]["open"])
    ema50 = float(signal["ema50"])
    ema200 = float(signal["ema200"])
    close = float(signal["close"])
    low = float(signal["low"])
    high = float(signal["high"])
    ema50_slope = float(signal["ema50"] - previous["ema50"])
    levels = recent_support_resistance(frame, entry_index - 1, lookback=32)

    if ema50 > ema200 and ema50_slope > 0 and low <= ema50 <= close and float(signal["rsi"]) >= 48:
        return build_setup(
            "trend_following",
            "BUY",
            frame,
            entry_index,
            entry,
            atr * 1.5,
            2.0,
            "ema50 pullback in uptrend",
            support_level=ema50,
            resistance_level=levels["resistance"],
            entry_trigger=f"closed back above EMA50 support {ema50:.2f}",
            level_source="EMA50 pullback + rolling_32 high/low",
            confirmation_checklist=(
                "EMA50 > EMA200",
                "EMA50 slope is rising",
                "signal candle tagged EMA50",
                "signal candle closed back above EMA50",
                "RSI >= 48",
            ),
            confluence_notes=("trend aligned", "pullback to dynamic support", "momentum not weak"),
            max_hold_bars=48,
        )
    if ema50 < ema200 and ema50_slope < 0 and high >= ema50 >= close and float(signal["rsi"]) <= 52:
        return build_setup(
            "trend_following",
            "SELL",
            frame,
            entry_index,
            entry,
            atr * 1.5,
            2.0,
            "ema50 pullback in downtrend",
            support_level=levels["support"],
            resistance_level=ema50,
            entry_trigger=f"closed back below EMA50 resistance {ema50:.2f}",
            level_source="EMA50 pullback + rolling_32 high/low",
            confirmation_checklist=(
                "EMA50 < EMA200",
                "EMA50 slope is falling",
                "signal candle tagged EMA50",
                "signal candle closed back below EMA50",
                "RSI <= 52",
            ),
            confluence_notes=("trend aligned", "pullback to dynamic resistance", "momentum not weak"),
            max_hold_bars=48,
        )
    return None


def breakout_setup(frame: Any, entry_index: int, symbol: str) -> TradeSetup | None:
    signal = frame.iloc[entry_index - 1]
    previous_window = frame.iloc[max(0, entry_index - 1 - 16) : entry_index - 1]
    if len(previous_window) < 16 or has_nan(signal, ("atr", "atr_median")):
        return None
    if local_session(str(signal["time"])) not in {"london", "new_york"}:
        return None
    atr = float(signal["atr"])
    if atr <= 0 or atr < float(signal["atr_median"]) * 1.05:
        return None
    high = float(previous_window["high"].max())
    low = float(previous_window["low"].min())
    close = float(signal["close"])
    entry = float(frame.iloc[entry_index]["open"])
    if close > high:
        return build_setup(
            "breakout",
            "BUY",
            frame,
            entry_index,
            entry,
            atr * 1.2,
            1.8,
            "range high breakout with atr expansion",
            support_level=low,
            resistance_level=high,
            entry_trigger=f"closed above resistance {high:.2f}",
            level_source="rolling_16 range high/low",
            confirmation_checklist=(
                "local session is London or New York",
                "close breaks above rolling resistance",
                "ATR is above its median expansion filter",
                "entry waits for next candle open",
            ),
            confluence_notes=("session liquidity window", "range breakout", "volatility expansion"),
            max_hold_bars=32,
        )
    if close < low:
        return build_setup(
            "breakout",
            "SELL",
            frame,
            entry_index,
            entry,
            atr * 1.2,
            1.8,
            "range low breakout with atr expansion",
            support_level=low,
            resistance_level=high,
            entry_trigger=f"closed below support {low:.2f}",
            level_source="rolling_16 range high/low",
            confirmation_checklist=(
                "local session is London or New York",
                "close breaks below rolling support",
                "ATR is above its median expansion filter",
                "entry waits for next candle open",
            ),
            confluence_notes=("session liquidity window", "range breakout", "volatility expansion"),
            max_hold_bars=32,
        )
    return None


def pullback_continuation_setup(frame: Any, entry_index: int, symbol: str) -> TradeSetup | None:
    signal = frame.iloc[entry_index - 1]
    previous = frame.iloc[entry_index - 2]
    fields = ("h1_ema50", "h1_ema200", "rsi", "macd", "macd_signal", "macd_hist", "atr")
    if has_nan(signal, fields) or has_nan(previous, ("rsi", "macd_hist")):
        return None
    atr = float(signal["atr"])
    if atr <= 0:
        return None
    entry = float(frame.iloc[entry_index]["open"])
    uptrend = float(signal["h1_ema50"]) > float(signal["h1_ema200"])
    downtrend = float(signal["h1_ema50"]) < float(signal["h1_ema200"])
    rsi = float(signal["rsi"])
    prev_rsi = float(previous["rsi"])
    hist = float(signal["macd_hist"])
    prev_hist = float(previous["macd_hist"])
    levels = recent_support_resistance(frame, entry_index - 1, lookback=32)

    if uptrend and prev_rsi <= 45 < rsi <= 62 and hist > prev_hist and hist > -0.1 * atr:
        return build_setup(
            "pullback_continuation",
            "BUY",
            frame,
            entry_index,
            entry,
            atr * 1.4,
            1.8,
            "h1 uptrend rsi/macd recovery",
            support_level=levels["support"],
            resistance_level=levels["resistance"],
            entry_trigger="H1 uptrend + M15 RSI recovered above 45 + MACD histogram improving",
            level_source="H1 EMA trend + M15 rolling_32 high/low",
            confirmation_checklist=(
                "H1 EMA50 > EMA200",
                "M15 RSI recovers through 45",
                "MACD histogram improves",
                "entry waits for next candle open",
            ),
            confluence_notes=("higher timeframe trend", "pullback recovery", "MACD momentum improvement"),
            max_hold_bars=48,
        )
    if downtrend and prev_rsi >= 55 > rsi >= 38 and hist < prev_hist and hist < 0.1 * atr:
        return build_setup(
            "pullback_continuation",
            "SELL",
            frame,
            entry_index,
            entry,
            atr * 1.4,
            1.8,
            "h1 downtrend rsi/macd rollover",
            support_level=levels["support"],
            resistance_level=levels["resistance"],
            entry_trigger="H1 downtrend + M15 RSI rolled below 55 + MACD histogram weakening",
            level_source="H1 EMA trend + M15 rolling_32 high/low",
            confirmation_checklist=(
                "H1 EMA50 < EMA200",
                "M15 RSI rolls below 55",
                "MACD histogram weakens",
                "entry waits for next candle open",
            ),
            confluence_notes=("higher timeframe trend", "pullback rollover", "MACD momentum weakening"),
            max_hold_bars=48,
        )
    return None


def mean_reversion_setup(frame: Any, entry_index: int, symbol: str) -> TradeSetup | None:
    signal = frame.iloc[entry_index - 1]
    previous_window = frame.iloc[max(0, entry_index - 1 - 32) : entry_index - 1]
    if len(previous_window) < 32 or has_nan(signal, ("ema50", "ema200", "atr", "atr_median", "rsi")):
        return None
    atr = float(signal["atr"])
    if atr <= 0 or atr > float(signal["atr_median"]) * 1.05:
        return None
    trend_distance = abs(float(signal["ema50"]) - float(signal["ema200"]))
    if trend_distance > atr * 1.2:
        return None
    support = float(previous_window["low"].min())
    resistance = float(previous_window["high"].max())
    entry = float(frame.iloc[entry_index]["open"])
    if float(signal["low"]) <= support + atr * 0.15 and float(signal["close"]) > float(signal["open"]) and float(signal["rsi"]) <= 42:
        return build_setup(
            "mean_reversion",
            "BUY",
            frame,
            entry_index,
            entry,
            atr * 1.0,
            1.2,
            "support bounce in low volatility range",
            support_level=support,
            resistance_level=resistance,
            entry_trigger=f"bullish rejection near support {support:.2f}",
            level_source="rolling_32 support/resistance range",
            confirmation_checklist=(
                "ATR is at or below low-volatility filter",
                "EMA50/EMA200 distance is not trending strongly",
                "price rejects rolling support",
                "RSI <= 42",
            ),
            confluence_notes=("range regime", "support rejection", "oversold pressure"),
            max_hold_bars=24,
        )
    if float(signal["high"]) >= resistance - atr * 0.15 and float(signal["close"]) < float(signal["open"]) and float(signal["rsi"]) >= 58:
        return build_setup(
            "mean_reversion",
            "SELL",
            frame,
            entry_index,
            entry,
            atr * 1.0,
            1.2,
            "resistance rejection in low volatility range",
            support_level=support,
            resistance_level=resistance,
            entry_trigger=f"bearish rejection near resistance {resistance:.2f}",
            level_source="rolling_32 support/resistance range",
            confirmation_checklist=(
                "ATR is at or below low-volatility filter",
                "EMA50/EMA200 distance is not trending strongly",
                "price rejects rolling resistance",
                "RSI >= 58",
            ),
            confluence_notes=("range regime", "resistance rejection", "overbought pressure"),
            max_hold_bars=24,
        )
    return None


def build_setup(
    family: str,
    side: str,
    frame: Any,
    entry_index: int,
    entry: float,
    stop_distance: float,
    reward_risk: float,
    reason: str,
    *,
    support_level: float | None,
    resistance_level: float | None,
    entry_trigger: str,
    level_source: str,
    confirmation_checklist: tuple[str, ...],
    confluence_notes: tuple[str, ...],
    max_hold_bars: int,
) -> TradeSetup:
    if side == "BUY":
        stop = entry - stop_distance
        target = entry + stop_distance * reward_risk
    else:
        stop = entry + stop_distance
        target = entry - stop_distance * reward_risk
    return TradeSetup(
        strategy=family,
        family=family,
        side=side,
        signal_index=entry_index - 1,
        entry_index=entry_index,
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        stop_distance=stop_distance,
        reward_risk=reward_risk,
        max_hold_bars=max_hold_bars,
        reason=reason,
        support_level=round(support_level, 4) if support_level is not None else None,
        resistance_level=round(resistance_level, 4) if resistance_level is not None else None,
        level_source=level_source,
        entry_trigger=entry_trigger,
        exit_plan=(
            f"stop {stop:.2f}, partial at 1R, move stop to breakeven after 1R, "
            f"take_profit {target:.2f}, time stop after {max_hold_bars} bars"
        ),
        confirmation_checklist=confirmation_checklist,
        confluence_score=confluence_score(confirmation_checklist, support_level, resistance_level),
        confluence_notes=confluence_notes,
    )


def exit_for_bar(setup: TradeSetup, bar: Any) -> tuple[float | None, str | None]:
    high = float(bar["high"])
    low = float(bar["low"])
    if setup.side == "BUY":
        hit_stop = low <= setup.stop_loss
        hit_take = high >= setup.take_profit
    else:
        hit_stop = high >= setup.stop_loss
        hit_take = low <= setup.take_profit
    if hit_stop:
        return setup.stop_loss, "stop_loss"
    if hit_take:
        return setup.take_profit, "take_profit"
    return None, None


def close_trade(setup: TradeSetup, frame: Any, exit_index: int, exit_price: float, exit_reason: str | None) -> dict[str, Any]:
    risk = abs(setup.entry_price - setup.stop_loss)
    price_move = exit_price - setup.entry_price if setup.side == "BUY" else setup.entry_price - exit_price
    r_multiple = price_move / risk if risk > 0 else 0.0
    return {
        **asdict(setup),
        "signal_time": str(frame.iloc[setup.signal_index]["time"]),
        "entry_time": str(frame.iloc[setup.entry_index]["time"]),
        "exit_time": str(frame.iloc[exit_index]["time"]),
        "exit_bar_index": exit_index,
        "bars_held": exit_index - setup.entry_index,
        "exit_price": exit_price,
        "exit_reason": exit_reason or "unknown",
        "management_plan": trade_management_plan(setup),
        "r_multiple": round(r_multiple, 6),
    }


def calculate_r_metrics(trades: list[Mapping[str, Any]]) -> dict[str, Any]:
    values = [float(trade["r_multiple"]) for trade in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    net_r = sum(values)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trade_count": len(values),
        "net_r": round(net_r, 4),
        "average_r": round(net_r / len(values), 4) if values else 0.0,
        "win_rate": round(len(wins) / len(values), 4) if values else 0.0,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (None if gross_win == 0 else 999.0),
        "max_drawdown_r": round(max_drawdown(values), 4),
        "max_consecutive_losses": max_consecutive_losses(values),
        "buy_count": sum(1 for trade in trades if trade["side"] == "BUY"),
        "sell_count": sum(1 for trade in trades if trade["side"] == "SELL"),
    }


def decide_strategy_status(
    metrics: Mapping[str, Any],
    train_metrics: Mapping[str, Any],
    test_metrics: Mapping[str, Any],
) -> tuple[str, str]:
    trades = int(metrics["trade_count"])
    if trades == 0:
        return ("NO_TRADES", "strategy generated no historical trades")
    if int(test_metrics["trade_count"]) < 5:
        return ("INSUFFICIENT_OOS_TRADES", "out-of-sample trade count is too small")
    if float(metrics["net_r"]) > 0 and float(test_metrics["net_r"]) > 0 and profit_factor_value(test_metrics) >= 1.15:
        return ("RESEARCH_CANDIDATE", "positive total and out-of-sample R without spread costs")
    if float(train_metrics["net_r"]) > 0 and float(test_metrics["net_r"]) <= 0:
        return ("OVERFIT_RISK", "train segment is positive but out-of-sample segment is not")
    return ("FAIL", "historical R metrics do not justify further work")


def decide_report_status(rows: list[Mapping[str, Any]], *, min_trades: int) -> tuple[str, str]:
    candidates = [
        row
        for row in rows
        if row["status"] == "RESEARCH_CANDIDATE" and int(row["trade_count"]) >= min_trades
    ]
    if candidates:
        return ("RESEARCH_CANDIDATES_FOUND", f"{len(candidates)} strategy rows pass no-spread historical research gates")
    if any(row["trade_count"] > 0 for row in rows):
        return ("NO_PASSING_STRATEGY", "strategies traded historically but none passed out-of-sample research gates")
    return ("NO_TRADES", "none of the strategy families generated trades")


def rank_strategies(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            row["status"] == "RESEARCH_CANDIDATE",
            float(row["test_metrics"]["net_r"]),
            float(row["metrics"]["net_r"]),
            -float(row["metrics"]["max_drawdown_r"]),
        ),
        reverse=True,
    )
    return [
        {
            "name": row["name"],
            "family": row["family"],
            "timeframe": row["timeframe"],
            "status": row["status"],
            "trade_count": row["trade_count"],
            "net_r": row["metrics"]["net_r"],
            "test_net_r": row["test_metrics"]["net_r"],
            "profit_factor": row["metrics"]["profit_factor"],
            "max_drawdown_r": row["metrics"]["max_drawdown_r"],
        }
        for row in ranked
    ]


def next_actions(rows: list[Mapping[str, Any]]) -> list[str]:
    candidates = [row for row in rows if row["status"] == "RESEARCH_CANDIDATE"]
    if not candidates:
        return [
            "Do not turn on trading; no strategy passed no-spread out-of-sample gates.",
            "Broaden historical data before tuning parameters.",
            "Keep production EA and risk gates unchanged.",
        ]
    return [
        "Treat passing rows as research candidates only; run walk-forward and spread/slippage stress next.",
        "Do not deploy until the candidate survives transaction-cost modeling and forward demo evidence.",
        "Keep production EA and risk gates unchanged.",
    ]


def current_level_snapshot(prepared: Mapping[str, Any]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for timeframe, frame in prepared.items():
        if len(frame) < 40:
            continue
        latest_index = len(frame) - 1
        latest = frame.iloc[latest_index]
        levels = recent_support_resistance(frame, latest_index, lookback=32)
        references = reference_levels(frame, latest_index)
        atr = float(latest["atr"]) if latest["atr"] == latest["atr"] else None
        last_close = float(latest["close"])
        trend = trend_label(latest)
        nearest = nearest_reference_levels(last_close, references)
        snapshot[timeframe] = {
            "time": str(latest["time"]),
            "last_close": round(last_close, 4),
            "trend": trend,
            "atr": round(atr, 4) if atr is not None else None,
            "support": levels["support"],
            "resistance": levels["resistance"],
            "reference_levels": references,
            "nearest_reference_levels": nearest,
            "entry_exit_plans": level_entry_exit_plans(last_close, levels, atr),
        }
    return snapshot


def level_entry_exit_plans(last_close: float, levels: Mapping[str, float | None], atr: float | None) -> list[dict[str, Any]]:
    support = levels.get("support")
    resistance = levels.get("resistance")
    if support is None or resistance is None or atr is None or atr <= 0:
        return []
    buffer = atr * 0.10
    return [
        {
            "plan": "breakout_buy",
            "direction": "BUY",
            "setup_type": "breakout",
            "trigger": round(resistance + buffer, 4),
            "entry_rule": "only after a candle closes above resistance plus buffer",
            "confirmation_required": [
                "close above resistance plus buffer",
                "ATR is not compressed",
                "no immediate rejection back into range",
            ],
            "stop_loss": round(resistance - atr * 0.80, 4),
            "take_profit_1r": round((resistance + buffer) + atr * 0.80, 4),
            "take_profit": round(resistance + atr * 1.80, 4),
            "invalid_if": round(support, 4),
            "move_stop_to_breakeven_at": round((resistance + buffer) + atr * 0.80, 4),
            "trail_after": round((resistance + buffer) + atr * 1.20, 4),
            "max_hold_bars": 32,
            "confluence_score": 60,
        },
        {
            "plan": "breakout_sell",
            "direction": "SELL",
            "setup_type": "breakout",
            "trigger": round(support - buffer, 4),
            "entry_rule": "only after a candle closes below support minus buffer",
            "confirmation_required": [
                "close below support minus buffer",
                "ATR is not compressed",
                "no immediate rejection back into range",
            ],
            "stop_loss": round(support + atr * 0.80, 4),
            "take_profit_1r": round((support - buffer) - atr * 0.80, 4),
            "take_profit": round(support - atr * 1.80, 4),
            "invalid_if": round(resistance, 4),
            "move_stop_to_breakeven_at": round((support - buffer) - atr * 0.80, 4),
            "trail_after": round((support - buffer) - atr * 1.20, 4),
            "max_hold_bars": 32,
            "confluence_score": 60,
        },
        {
            "plan": "support_reversal_buy",
            "direction": "BUY",
            "setup_type": "mean_reversion",
            "trigger_zone": [round(support, 4), round(support + atr * 0.15, 4)],
            "entry_rule": "wait for bullish rejection inside support zone",
            "confirmation_required": [
                "price trades into support zone",
                "bullish rejection candle closes back above support",
                "do not enter if support breaks and closes below invalidation",
            ],
            "stop_loss": round(support - atr, 4),
            "take_profit_1r": round(support + atr, 4),
            "take_profit": round(min(resistance, last_close + atr * 1.20), 4),
            "invalid_if": round(support - atr * 0.25, 4),
            "move_stop_to_breakeven_at": round(support + atr, 4),
            "trail_after": round(support + atr * 1.5, 4),
            "max_hold_bars": 24,
            "confluence_score": 55,
        },
        {
            "plan": "resistance_reversal_sell",
            "direction": "SELL",
            "setup_type": "mean_reversion",
            "trigger_zone": [round(resistance - atr * 0.15, 4), round(resistance, 4)],
            "entry_rule": "wait for bearish rejection inside resistance zone",
            "confirmation_required": [
                "price trades into resistance zone",
                "bearish rejection candle closes back below resistance",
                "do not enter if resistance breaks and closes above invalidation",
            ],
            "stop_loss": round(resistance + atr, 4),
            "take_profit_1r": round(resistance - atr, 4),
            "take_profit": round(max(support, last_close - atr * 1.20), 4),
            "invalid_if": round(resistance + atr * 0.25, 4),
            "move_stop_to_breakeven_at": round(resistance - atr, 4),
            "trail_after": round(resistance - atr * 1.5, 4),
            "max_hold_bars": 24,
            "confluence_score": 55,
        },
    ]


def trade_management_plan(setup: TradeSetup) -> dict[str, Any]:
    if setup.side == "BUY":
        take_profit_1r = setup.entry_price + setup.stop_distance
        breakeven = take_profit_1r
        trail_after = setup.entry_price + setup.stop_distance * 1.5
    else:
        take_profit_1r = setup.entry_price - setup.stop_distance
        breakeven = take_profit_1r
        trail_after = setup.entry_price - setup.stop_distance * 1.5
    return {
        "initial_stop_loss": round(setup.stop_loss, 4),
        "partial_take_profit_at_1r": round(take_profit_1r, 4),
        "move_stop_to_breakeven_at": round(breakeven, 4),
        "final_take_profit": round(setup.take_profit, 4),
        "trail_after": round(trail_after, 4),
        "time_stop_bars": setup.max_hold_bars,
        "risk_reward": setup.reward_risk,
        "rule": "historical research plan only; not wired to live execution",
    }


def confluence_score(
    confirmation_checklist: tuple[str, ...],
    support_level: float | None,
    resistance_level: float | None,
) -> int:
    score = 25 + min(45, len(confirmation_checklist) * 9)
    if support_level is not None:
        score += 10
    if resistance_level is not None:
        score += 10
    return min(100, score)


def reference_levels(frame: Any, latest_index: int) -> dict[str, Any]:
    latest_levels = {
        "rolling_16": recent_support_resistance(frame, latest_index, lookback=16),
        "rolling_32": recent_support_resistance(frame, latest_index, lookback=32),
        "rolling_96": recent_support_resistance(frame, latest_index, lookback=96),
        "previous_day": previous_local_day_levels(frame, latest_index),
    }
    return latest_levels


def previous_local_day_levels(frame: Any, latest_index: int) -> dict[str, float | str | None]:
    import pandas as pd

    if latest_index <= 0 or frame.empty:
        return {"date": None, "high": None, "low": None, "close": None, "pivot": None}
    data = frame.iloc[:latest_index].copy()
    data["local_date"] = pd.to_datetime(data["time"], utc=True).dt.tz_convert("Asia/Shanghai").dt.date
    current_date = pd.Timestamp(frame.iloc[latest_index]["time"]).tz_convert("Asia/Shanghai").date()
    previous_dates = sorted(date for date in data["local_date"].dropna().unique() if date < current_date)
    if not previous_dates:
        return {"date": None, "high": None, "low": None, "close": None, "pivot": None}
    date = previous_dates[-1]
    previous = data[data["local_date"] == date]
    high = float(previous["high"].max())
    low = float(previous["low"].min())
    close = float(previous.iloc[-1]["close"])
    return {
        "date": str(date),
        "high": round(high, 4),
        "low": round(low, 4),
        "close": round(close, 4),
        "pivot": round((high + low + close) / 3.0, 4),
    }


def nearest_reference_levels(last_close: float, references: Mapping[str, Any]) -> dict[str, Any]:
    supports: list[dict[str, Any]] = []
    resistances: list[dict[str, Any]] = []
    for source, levels in references.items():
        if not isinstance(levels, Mapping):
            continue
        for name, value in levels.items():
            if name == "date":
                continue
            if value is None:
                continue
            price = float(value)
            item = {"source": source, "level": name, "price": round(price, 4), "distance": round(abs(last_close - price), 4)}
            if price <= last_close:
                supports.append(item)
            else:
                resistances.append(item)
    supports.sort(key=lambda item: item["distance"])
    resistances.sort(key=lambda item: item["distance"])
    return {
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
    }


def trend_label(row: Any) -> str:
    if row.get("ema50") != row.get("ema50") or row.get("ema200") != row.get("ema200"):
        return "unknown"
    ema50 = float(row["ema50"])
    ema200 = float(row["ema200"])
    close = float(row["close"])
    if close > ema50 > ema200:
        return "uptrend"
    if close < ema50 < ema200:
        return "downtrend"
    return "range_or_transition"


def recent_support_resistance(frame: Any, signal_index: int, *, lookback: int) -> dict[str, float | None]:
    start = max(0, signal_index - lookback)
    window = frame.iloc[start:signal_index]
    if window.empty:
        return {"support": None, "resistance": None}
    support = float(window["low"].min())
    resistance = float(window["high"].max())
    return {
        "support": round(support, 4),
        "resistance": round(resistance, 4),
    }


def prepare_timeframes(bars_m15: Any) -> dict[str, Any]:
    m15 = add_indicators(bars_m15.copy())
    h1 = add_indicators(resample_ohlcv(bars_m15, "1h"))
    h4 = add_indicators(resample_ohlcv(bars_m15, "4h"))
    h1_context = h1[["time", "ema50", "ema200"]].rename(columns={"ema50": "h1_ema50", "ema200": "h1_ema200"})
    m15 = merge_asof_context(m15, h1_context)
    return {"M15": m15, "H1": h1, "H4": h4}


def add_indicators(frame: Any) -> Any:
    frame = frame.copy().reset_index(drop=True)
    frame["ema50"] = frame["close"].ewm(span=50, adjust=False).mean()
    frame["ema200"] = frame["close"].ewm(span=200, adjust=False).mean()
    previous_close = frame["close"].shift(1)
    true_range = frame[["high", "low"]].assign(
        high_close=(frame["high"] - previous_close).abs(),
        low_close=(frame["low"] - previous_close).abs(),
        high_low=frame["high"] - frame["low"],
    )[["high_close", "low_close", "high_low"]].max(axis=1)
    frame["atr"] = true_range.rolling(14).mean()
    frame["atr_median"] = frame["atr"].rolling(50).median()
    frame["rsi"] = rsi(frame["close"], 14)
    ema12 = frame["close"].ewm(span=12, adjust=False).mean()
    ema26 = frame["close"].ewm(span=26, adjust=False).mean()
    frame["macd"] = ema12 - ema26
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False).mean()
    frame["macd_hist"] = frame["macd"] - frame["macd_signal"]
    return frame


def rsi(series: Any, period: int) -> Any:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def resample_ohlcv(frame: Any, rule: str) -> Any:
    indexed = frame.copy()
    indexed["time"] = to_datetime(indexed["time"])
    indexed = indexed.set_index("time")
    out = indexed.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
            "spread": "median",
            "real_volume": "sum",
        }
    )
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index()
    return out


def merge_asof_context(frame: Any, context: Any) -> Any:
    import pandas as pd

    left = frame.copy()
    right = context.copy()
    left["time"] = to_datetime(left["time"])
    right["time"] = to_datetime(right["time"])
    return pd.merge_asof(left.sort_values("time"), right.sort_values("time"), on="time", direction="backward")


def load_bars(path: Path, pd: Any) -> Any:
    frame = pd.read_csv(path)
    if frame.empty:
        return frame
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "tick_volume", "spread", "real_volume"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def to_datetime(series: Any) -> Any:
    import pandas as pd

    return pd.to_datetime(series, utc=True)


def local_session(timestamp_text: str) -> str:
    import pandas as pd

    hour = pd.Timestamp(timestamp_text).tz_convert("Asia/Shanghai").hour
    if 15 <= hour <= 20:
        return "london"
    if hour >= 21 or hour <= 4:
        return "new_york"
    return "other"


def has_nan(row: Any, fields: Iterable[str]) -> bool:
    for field in fields:
        value = row[field]
        if value != value:
            return True
    return False


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def max_consecutive_losses(values: list[float]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def profit_factor_value(metrics: Mapping[str, Any]) -> float:
    value = metrics.get("profit_factor")
    return 0.0 if value is None else float(value)


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader strategy four-pack report")
    print(f"campaign: {report['campaign_version']}")
    print(f"status: {report['status']}")
    print(f"reason: {report['reason']}")
    print(f"no_spread_cost_mode: {report['no_spread_cost_mode']}")
    print("current support/resistance levels:")
    for timeframe, levels in report.get("current_level_snapshot", {}).items():
        print(
            f"  {timeframe}: close={levels['last_close']} trend={levels['trend']} "
            f"support={levels['support']} resistance={levels['resistance']} atr={levels['atr']}"
        )
        nearest = levels.get("nearest_reference_levels", {})
        if nearest:
            print(
                f"    nearest_support={nearest.get('nearest_support')} "
                f"nearest_resistance={nearest.get('nearest_resistance')}"
            )
        for plan in levels.get("entry_exit_plans", []):
            trigger = plan.get("trigger", plan.get("trigger_zone"))
            print(
                f"    {plan['plan']}: trigger={trigger} stop={plan['stop_loss']} "
                f"tp1={plan.get('take_profit_1r')} tp2={plan['take_profit']} "
                f"be={plan.get('move_stop_to_breakeven_at')} invalid_if={plan['invalid_if']} "
                f"score={plan.get('confluence_score')}"
            )
    print("ranking:")
    for row in report["ranking"]:
        print(
            f"  {row['name']}: {row['status']} | trades={row['trade_count']} "
            f"net_r={row['net_r']} test_net_r={row['test_net_r']} "
            f"pf={row['profit_factor']} dd_r={row['max_drawdown_r']}"
        )
    print("next:")
    for action in report["next_actions"]:
        print(f"  - {action}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v0.26.2 no-spread four-family strategy research.")
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--symbol", default="GOLD_")
    parser.add_argument("--timeframe", default="M15")
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--min-trades", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
