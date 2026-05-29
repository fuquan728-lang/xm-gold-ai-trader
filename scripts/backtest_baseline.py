from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator
from src.strategy.risk_manager import AccountState, RiskConfig, RiskManager, SymbolSpec, TradeRiskRequest


@dataclass(slots=True)
class BacktestPosition:
    side: str
    volume: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float | None
    entry_time: str


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="backtest_baseline")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for backtesting. Install requirements.txt.") from exc

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    bars = pd.read_csv(input_path)
    bars.columns = [column.lower() for column in bars.columns]
    required = {"open", "high", "low", "close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"input CSV is missing columns: {sorted(missing)}")

    if "time" in bars.columns:
        bars["time"] = pd.to_datetime(bars["time"], utc=True)

    try:
        with MT5Client(build_connection_config(args)) as client:
            symbol_info = client.get_symbol_info(args.symbol)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    risk_config = RiskConfig(
        risk_per_trade_pct=args.risk_per_trade_pct,
        max_daily_loss_pct=args.max_daily_loss_pct,
        max_spread_points=args.max_spread_points,
        one_position_only=True,
        max_lot_per_trade=args.max_lot_per_trade,
    )
    result = run_backtest(
        bars=bars,
        symbol=args.symbol,
        symbol_info=symbol_info.raw,
        initial_balance=args.initial_balance,
        risk_config=risk_config,
        spread_points=args.spread_points if args.spread_points is not None else float(symbol_info.spread),
    )
    result["input_csv"] = str(input_path)
    result["input_sha256"] = sha256_file(input_path)
    result["symbol_info_source"] = f'MetaTrader5.symbol_info("{args.symbol}")'
    result["symbol_info"] = symbol_info.raw
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    logger.info("Wrote backtest report to %s", output_path)
    print(json.dumps(result["metrics"], indent=2, sort_keys=True))
    return 0


def run_backtest(
    *,
    bars: Any,
    symbol: str,
    symbol_info: dict[str, Any],
    initial_balance: float,
    risk_config: RiskConfig,
    spread_points: float,
) -> dict[str, Any]:
    generator = BaselineSignalGenerator(BaselineSignalConfig())
    risk_manager = RiskManager(risk_config)
    symbol_spec = SymbolSpec.from_mt5(symbol_info)

    balance = float(initial_balance)
    position: BacktestPosition | None = None
    trades: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    daily_pnl: dict[str, float] = {}
    minimum_bars = max(generator.config.slow_sma, generator.config.atr_period) + 2

    for index in range(minimum_bars, len(bars)):
        bar = bars.iloc[index]
        bar_time = _bar_time(bar, index)
        day_key = bar_time[:10]

        if position is not None:
            exit_price, exit_reason = _exit_price(position, bar)
            if exit_price is not None:
                pnl = _price_move_pnl(symbol_spec, position.side, position.volume, position.entry_price, exit_price)
                balance += pnl
                daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + pnl
                trades.append(
                    {
                        "entry_time": position.entry_time,
                        "exit_time": bar_time,
                        "side": position.side,
                        "volume": position.volume,
                        "entry_price": position.entry_price,
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "reason": exit_reason,
                    }
                )
                position = None
            continue

        signal = generator.generate(bars.iloc[:index], symbol)
        if not signal.is_actionable:
            continue

        entry_price = float(bar["open"])
        stop_loss = float(signal.stop_loss_price)
        if signal.side == "BUY" and stop_loss >= entry_price:
            continue
        if signal.side == "SELL" and stop_loss <= entry_price:
            continue

        take_profit = _project_take_profit(signal.side, entry_price, stop_loss, generator.config.reward_risk_ratio)
        risk_decision = risk_manager.assess_trade(
            TradeRiskRequest(
                symbol_info=symbol_info,
                account=AccountState(
                    balance=balance,
                    equity=balance,
                    daily_realized_pnl=daily_pnl.get(day_key, 0.0),
                ),
                side=signal.side,
                entry_price=entry_price,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                current_spread_points=spread_points,
                open_positions=(),
            )
        )
        if not risk_decision.allowed:
            blocked.append({"time": bar_time, "side": signal.side, "reasons": risk_decision.reasons})
            continue

        position = BacktestPosition(
            side=signal.side,
            volume=risk_decision.volume,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            entry_time=bar_time,
        )

    if position is not None and len(bars) > 0:
        final_bar = bars.iloc[-1]
        final_time = _bar_time(final_bar, len(bars) - 1)
        exit_price = float(final_bar["close"])
        pnl = _price_move_pnl(symbol_spec, position.side, position.volume, position.entry_price, exit_price)
        balance += pnl
        trades.append(
            {
                "entry_time": position.entry_time,
                "exit_time": final_time,
                "side": position.side,
                "volume": position.volume,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "reason": "end_of_data",
            }
        )

    total_pnl = balance - initial_balance
    winners = [trade for trade in trades if trade["pnl"] > 0]
    losers = [trade for trade in trades if trade["pnl"] <= 0]
    metrics = {
        "initial_balance": initial_balance,
        "ending_balance": balance,
        "total_pnl": total_pnl,
        "return_pct": (total_pnl / initial_balance) * 100.0 if initial_balance else 0.0,
        "trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "win_rate_pct": (len(winners) / len(trades)) * 100.0 if trades else 0.0,
        "blocked_signals": len(blocked),
    }
    return {
        "project": "xm-gold-ai-trader",
        "symbol": symbol,
        "risk_config": asdict(risk_config),
        "spread_points_used": spread_points,
        "metrics": metrics,
        "trades": trades,
        "blocked_signals": blocked,
        "notes": [
            "Backtest uses current MetaTrader5.symbol_info values for contract sizing.",
            "Historical commissions, swaps, and variable spreads are not modeled in this baseline.",
            "If a bar touches stop-loss and take-profit, stop-loss is assumed first.",
        ],
    }


def _exit_price(position: BacktestPosition, bar: Any) -> tuple[float | None, str | None]:
    high = float(bar["high"])
    low = float(bar["low"])
    if position.side == "BUY":
        hit_stop = low <= position.stop_loss_price
        hit_take_profit = position.take_profit_price is not None and high >= position.take_profit_price
    else:
        hit_stop = high >= position.stop_loss_price
        hit_take_profit = position.take_profit_price is not None and low <= position.take_profit_price
    if hit_stop:
        return position.stop_loss_price, "stop_loss"
    if hit_take_profit:
        return float(position.take_profit_price), "take_profit"
    return None, None


def _project_take_profit(side: str, entry: float, stop: float, reward_risk_ratio: float) -> float:
    risk_distance = abs(entry - stop)
    if side == "BUY":
        return entry + (risk_distance * reward_risk_ratio)
    return entry - (risk_distance * reward_risk_ratio)


def _price_move_pnl(spec: SymbolSpec, side: str, volume: float, entry: float, exit_price: float) -> float:
    price_delta = exit_price - entry if side == "BUY" else entry - exit_price
    ticks = price_delta / spec.trade_tick_size
    return ticks * spec.trade_tick_value * volume


def _bar_time(bar: Any, index: int) -> str:
    value = bar.get("time", None)
    if value is None:
        return str(index)
    return str(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest the cautious baseline GOLD_ strategy.")
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--output", default="reports/baseline_backtest.json")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--initial-balance", type=float, default=10_000.0)
    parser.add_argument("--risk-per-trade-pct", type=float, default=0.25)
    parser.add_argument("--max-daily-loss-pct", type=float, default=1.0)
    parser.add_argument("--max-spread-points", type=float, default=350.0)
    parser.add_argument("--max-lot-per-trade", type=float, default=None)
    parser.add_argument("--spread-points", type=float, default=None)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    return parser.parse_args()


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


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
