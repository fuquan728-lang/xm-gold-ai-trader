from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig
from src.strategy.risk_manager import AccountState, RiskConfig, RiskManager, SymbolSpec, TradeRiskRequest


PROJECT = "xm-gold-ai-trader"
MODE = "backtest_baseline_report"
REASON_NO_BACKTEST_DATA = "NO_BACKTEST_DATA"
REASON_NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    signal: BaselineSignalConfig
    risk: RiskConfig
    initial_balance: float = 10_000.0
    spread_points: float | None = None


@dataclass(slots=True)
class OpenPosition:
    side: str
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: str
    entry_bar_index: int
    signal_time: str
    signal_bar_index: int
    risk_amount: float
    risk_per_lot: float
    spread_cost: float


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="backtest_baseline_report")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for backtesting. Install requirements.txt.") from exc

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        bars, symbol_info, data_source = load_backtest_inputs(args, pd)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1

    config = BacktestConfig(
        signal=BaselineSignalConfig(
            fast_sma=args.fast_sma,
            slow_sma=args.slow_sma,
            atr_period=args.atr_period,
            atr_stop_multiplier=args.atr_stop_multiplier,
            reward_risk_ratio=args.reward_risk_ratio,
        ),
        risk=RiskConfig(
            risk_per_trade_pct=args.risk_per_trade_pct,
            max_daily_loss_pct=args.max_daily_loss_pct,
            max_spread_points=args.max_spread_points,
            one_position_only=True,
            max_lot_per_trade=args.max_lot_per_trade,
        ),
        initial_balance=args.initial_balance,
        spread_points=args.spread_points,
    )
    report = run_backtest_report(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        config=config,
        data_source=data_source,
    )
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str), encoding="utf-8")
    logger.info("Wrote baseline backtest report to %s", output_path)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(format_summary(report))
        print(f"\nJSON report: {output_path}")
    return 0


def load_backtest_inputs(args: argparse.Namespace, pd: Any) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    input_path = Path(args.input)
    if input_path.exists():
        bars = normalize_bars(pd.read_csv(input_path), pd)
        metadata = load_symbol_metadata(input_path.with_suffix(input_path.suffix + ".symbol_info.json"))
        if metadata is not None:
            return bars, dict(metadata["symbol_info"]), {
                "kind": "csv",
                "input": str(input_path),
                "input_sha256": sha256_file(input_path),
                "symbol_info_source": str(metadata.get("symbol_info_source", "collected metadata")),
            }

        with MT5Client(build_connection_config(args)) as client:
            symbol_info = client.get_symbol_info(args.symbol).raw
        return bars, symbol_info, {
            "kind": "csv_plus_mt5_symbol_info",
            "input": str(input_path),
            "input_sha256": sha256_file(input_path),
            "symbol_info_source": f'MetaTrader5.symbol_info("{args.symbol}")',
        }

    with MT5Client(build_connection_config(args)) as client:
        symbol_info = client.get_symbol_info(args.symbol).raw
        rates = client.copy_rates_from_pos(args.symbol, args.timeframe, args.bars, start_pos=1)
    bars = pd.DataFrame(rates)
    if "time" in bars.columns:
        bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)
    return normalize_bars(bars, pd), symbol_info, {
        "kind": "mt5_copy_rates",
        "bars": int(len(bars)),
        "symbol_info_source": f'MetaTrader5.symbol_info("{args.symbol}")',
    }


def normalize_bars(bars: Any, pd: Any) -> Any:
    frame = bars.copy()
    frame.columns = [str(column).lower() for column in frame.columns]
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"bars are missing required columns: {sorted(missing)}")
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").reset_index(drop=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column].astype(float)
    if "spread" in frame.columns:
        frame["spread"] = frame["spread"].astype(float)
    return frame


def load_symbol_metadata(path: Path) -> Mapping[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or not isinstance(payload.get("symbol_info"), Mapping):
        return None
    return payload


def run_backtest_report(
    *,
    bars: Any,
    symbol: str,
    timeframe: str,
    symbol_info: dict[str, Any],
    config: BacktestConfig,
    data_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_report = {
        "project": PROJECT,
        "mode": MODE,
        "orders_sent": 0,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "OK",
        "reason_codes": [],
        "data_source": data_source or {},
        "config": {
            "signal": asdict(config.signal),
            "risk": asdict(config.risk),
            "initial_balance": config.initial_balance,
            "spread_points": config.spread_points,
        },
        "metrics": empty_metrics(config.initial_balance),
        "trades": [],
        "blocked_signals": [],
        "notes": [
            "No AI model trading is used.",
            "No martingale, grid, or automatic lot increase after loss is modeled.",
            "Signals use the previous closed bar; entries occur at the next bar open.",
            "If a bar touches stop-loss and take-profit, stop-loss is assumed first.",
        ],
    }

    if len(bars) == 0:
        base_report["status"] = "NO_DATA"
        base_report["reason_codes"] = [REASON_NO_BACKTEST_DATA]
        return with_summary(base_report)

    minimum_bars = max(config.signal.slow_sma, config.signal.atr_period) + 2
    if len(bars) < minimum_bars:
        base_report["status"] = "NOT_ENOUGH_DATA"
        base_report["reason_codes"] = [REASON_NOT_ENOUGH_DATA]
        return with_summary(base_report)

    frame = add_indicators(bars, config.signal)
    spec = SymbolSpec.from_mt5(symbol_info)
    risk_manager = RiskManager(config.risk)
    balance = float(config.initial_balance)
    equity_curve = [balance]
    daily_pnl: dict[str, float] = {}
    open_position: OpenPosition | None = None
    trades: list[dict[str, Any]] = []
    blocked_signals: list[dict[str, Any]] = []

    for entry_index in range(minimum_bars, len(frame)):
        bar = frame.iloc[entry_index]
        bar_time = bar_time_text(bar)
        day_key = bar_time[:10]

        if open_position is not None:
            exit_price, exit_reason = exit_price_for_bar(open_position, bar)
            if exit_price is not None:
                trade = close_position(
                    position=open_position,
                    exit_price=exit_price,
                    exit_time=bar_time,
                    exit_bar_index=entry_index,
                    exit_reason=str(exit_reason),
                    spec=spec,
                )
                balance += float(trade["pnl"])
                equity_curve.append(balance)
                daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + float(trade["pnl"])
                trades.append(trade)
                open_position = None
            continue

        signal = signal_from_previous_closed_bar(frame, entry_index, config.signal)
        if signal is None:
            continue

        entry_price = float(bar["open"])
        stop_distance = float(frame.iloc[entry_index - 1]["atr"]) * config.signal.atr_stop_multiplier
        if stop_distance <= 0:
            continue
        stop_loss = entry_price - stop_distance if signal == "BUY" else entry_price + stop_distance
        take_profit = (
            entry_price + (stop_distance * config.signal.reward_risk_ratio)
            if signal == "BUY"
            else entry_price - (stop_distance * config.signal.reward_risk_ratio)
        )
        spread_points = spread_points_for_bar(bar, config.spread_points, symbol_info)
        risk_decision = risk_manager.assess_trade(
            TradeRiskRequest(
                symbol_info=symbol_info,
                account=AccountState(
                    balance=balance,
                    equity=balance,
                    daily_realized_pnl=daily_pnl.get(day_key, 0.0),
                ),
                side=signal,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                current_spread_points=spread_points,
                open_positions=(),
            )
        )
        if not risk_decision.allowed:
            blocked_signals.append(
                {
                    "time": bar_time,
                    "bar_index": entry_index,
                    "side": signal,
                    "reason_codes": list(risk_decision.reason_codes),
                    "reasons": list(risk_decision.reasons),
                }
            )
            continue

        open_position = OpenPosition(
            side=signal,
            volume=risk_decision.volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=bar_time,
            entry_bar_index=entry_index,
            signal_time=bar_time_text(frame.iloc[entry_index - 1]),
            signal_bar_index=entry_index - 1,
            risk_amount=risk_decision.risk_per_lot * risk_decision.volume,
            risk_per_lot=risk_decision.risk_per_lot,
            spread_cost=spread_cost(spec, risk_decision.volume, spread_points),
        )

    if open_position is not None:
        final_index = len(frame) - 1
        final_bar = frame.iloc[final_index]
        trade = close_position(
            position=open_position,
            exit_price=float(final_bar["close"]),
            exit_time=bar_time_text(final_bar),
            exit_bar_index=final_index,
            exit_reason="end_of_data",
            spec=spec,
        )
        balance += float(trade["pnl"])
        equity_curve.append(balance)
        day_key = str(trade["exit_time"])[:10]
        daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + float(trade["pnl"])
        trades.append(trade)

    base_report["metrics"] = calculate_metrics(
        trades=trades,
        initial_balance=config.initial_balance,
        ending_balance=balance,
        equity_curve=equity_curve,
        daily_pnl=daily_pnl,
    )
    base_report["trades"] = trades
    base_report["blocked_signals"] = blocked_signals
    return with_summary(base_report)


def add_indicators(bars: Any, config: BaselineSignalConfig) -> Any:
    frame = bars.copy()
    frame["fast_sma"] = frame["close"].rolling(config.fast_sma).mean()
    frame["slow_sma"] = frame["close"].rolling(config.slow_sma).mean()
    previous_close = frame["close"].shift(1)
    true_range = frame[["high", "low"]].assign(
        high_close=(frame["high"] - previous_close).abs(),
        low_close=(frame["low"] - previous_close).abs(),
        high_low=frame["high"] - frame["low"],
    )[["high_close", "low_close", "high_low"]].max(axis=1)
    frame["atr"] = true_range.rolling(config.atr_period).mean()
    return frame


def signal_from_previous_closed_bar(frame: Any, entry_index: int, config: BaselineSignalConfig) -> str | None:
    previous = frame.iloc[entry_index - 2]
    signal_bar = frame.iloc[entry_index - 1]
    values = (
        previous["fast_sma"],
        previous["slow_sma"],
        signal_bar["fast_sma"],
        signal_bar["slow_sma"],
        signal_bar["atr"],
    )
    if any(value != value for value in values):
        return None
    crossed_up = previous["fast_sma"] <= previous["slow_sma"] and signal_bar["fast_sma"] > signal_bar["slow_sma"]
    crossed_down = previous["fast_sma"] >= previous["slow_sma"] and signal_bar["fast_sma"] < signal_bar["slow_sma"]
    if crossed_up:
        return "BUY"
    if crossed_down:
        return "SELL"
    return None


def exit_price_for_bar(position: OpenPosition, bar: Any) -> tuple[float | None, str | None]:
    high = float(bar["high"])
    low = float(bar["low"])
    if position.side == "BUY":
        hit_stop = low <= position.stop_loss
        hit_take_profit = high >= position.take_profit
    else:
        hit_stop = high >= position.stop_loss
        hit_take_profit = low <= position.take_profit
    if hit_stop:
        return position.stop_loss, "stop_loss"
    if hit_take_profit:
        return position.take_profit, "take_profit"
    return None, None


def close_position(
    *,
    position: OpenPosition,
    exit_price: float,
    exit_time: str,
    exit_bar_index: int,
    exit_reason: str,
    spec: SymbolSpec,
) -> dict[str, Any]:
    gross_pnl = price_move_pnl(spec, position.side, position.volume, position.entry_price, exit_price)
    pnl = gross_pnl - position.spread_cost
    r_multiple = pnl / position.risk_amount if position.risk_amount > 0 else 0.0
    return {
        "side": position.side,
        "volume": position.volume,
        "signal_time": position.signal_time,
        "signal_bar_index": position.signal_bar_index,
        "entry_time": position.entry_time,
        "entry_bar_index": position.entry_bar_index,
        "entry_price": position.entry_price,
        "stop_loss": position.stop_loss,
        "take_profit": position.take_profit,
        "exit_time": exit_time,
        "exit_bar_index": exit_bar_index,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_pnl_before_spread": gross_pnl,
        "spread_cost": position.spread_cost,
        "pnl": pnl,
        "r_multiple": r_multiple,
    }


def price_move_pnl(spec: SymbolSpec, side: str, volume: float, entry: float, exit_price: float) -> float:
    price_delta = exit_price - entry if side == "BUY" else entry - exit_price
    ticks = price_delta / spec.trade_tick_size
    return ticks * spec.trade_tick_value * volume


def spread_cost(spec: SymbolSpec, volume: float, spread_points: float) -> float:
    price_distance = spread_points * spec.point
    ticks = price_distance / spec.trade_tick_size
    return ticks * spec.trade_tick_value * volume


def spread_points_for_bar(bar: Any, configured_spread: float | None, symbol_info: Mapping[str, Any]) -> float:
    if configured_spread is not None:
        return float(configured_spread)
    if "spread" in bar and bar["spread"] == bar["spread"]:
        return float(bar["spread"])
    return float(symbol_info.get("spread", 0.0) or 0.0)


def calculate_metrics(
    *,
    trades: list[dict[str, Any]],
    initial_balance: float,
    ending_balance: float,
    equity_curve: list[float],
    daily_pnl: dict[str, float],
) -> dict[str, Any]:
    gross_profit = sum(float(trade["pnl"]) for trade in trades if float(trade["pnl"]) > 0)
    gross_loss = sum(float(trade["pnl"]) for trade in trades if float(trade["pnl"]) < 0)
    total_trades = len(trades)
    wins = [trade for trade in trades if float(trade["pnl"]) > 0]
    net_profit = ending_balance - initial_balance
    worst_day = None
    if daily_pnl:
        day, pnl = min(daily_pnl.items(), key=lambda item: item[1])
        worst_day = {"date": day, "pnl": pnl}
    return {
        "initial_balance": initial_balance,
        "ending_balance": ending_balance,
        "total_trades": total_trades,
        "win_rate": len(wins) / total_trades if total_trades else 0.0,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "net_profit": net_profit,
        "profit_factor": gross_profit / abs(gross_loss) if gross_loss < 0 else None,
        "max_drawdown": max_drawdown(equity_curve),
        "max_drawdown_pct": max_drawdown_pct(equity_curve),
        "average_r": sum(float(trade["r_multiple"]) for trade in trades) / total_trades if total_trades else 0.0,
        "max_consecutive_losses": max_consecutive_losses(trades),
        "worst_day": worst_day,
    }


def empty_metrics(initial_balance: float) -> dict[str, Any]:
    return calculate_metrics(
        trades=[],
        initial_balance=initial_balance,
        ending_balance=initial_balance,
        equity_curve=[initial_balance],
        daily_pnl={},
    )


def max_drawdown(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def max_drawdown_pct(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def max_consecutive_losses(trades: list[dict[str, Any]]) -> int:
    longest = 0
    current = 0
    for trade in trades:
        if float(trade["pnl"]) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def with_summary(report: dict[str, Any]) -> dict[str, Any]:
    report["summary"] = format_summary(report)
    return report


def format_summary(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]
    profit_factor = metrics["profit_factor"]
    profit_factor_text = "n/a" if profit_factor is None else f"{profit_factor:.2f}"
    worst_day = metrics["worst_day"]
    worst_day_text = "n/a" if not worst_day else f"{worst_day['date']} ({worst_day['pnl']:.2f})"
    return "\n".join(
        [
            "xm-gold-ai-trader baseline backtest",
            f"Symbol/timeframe: {report['symbol']} {report['timeframe']}",
            f"Status: {report['status']}",
            f"Trades: {metrics['total_trades']}",
            f"Win rate: {metrics['win_rate'] * 100:.2f}%",
            f"Net profit: {metrics['net_profit']:.2f}",
            f"Profit factor: {profit_factor_text}",
            f"Max drawdown: {metrics['max_drawdown']:.2f}",
            f"Average R: {metrics['average_r']:.3f}",
            f"Max consecutive losses: {metrics['max_consecutive_losses']}",
            f"Worst day: {worst_day_text}",
            "Orders sent: 0",
        ]
    )


def bar_time_text(bar: Any) -> str:
    return str(bar["time"])


def build_connection_config(args: argparse.Namespace) -> MT5ConnectionConfig:
    return MT5ConnectionConfig(
        symbol=args.symbol,
        terminal_path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
        timeout_ms=args.timeout_ms,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a baseline GOLD_ backtest report without sending orders.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--output", default="reports/backtests/baseline_report.json")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.25)
    parser.add_argument("--max-daily-loss-pct", type=float, default=1.0)
    parser.add_argument("--max-spread-points", type=float, default=350.0)
    parser.add_argument("--max-lot-per-trade", type=float, default=None)
    parser.add_argument("--spread-points", type=float, default=None)
    parser.add_argument("--fast-sma", type=int, default=20)
    parser.add_argument("--slow-sma", type=int, default=50)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--reward-risk-ratio", type=float, default=1.5)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
