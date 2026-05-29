from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.broker.order_executor import ExecutionResult, OrderExecutor, TradingConfig, load_trading_config
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator, TradeSignal
from src.strategy.risk_manager import RiskDecision, SymbolSpec


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="run_paper_trader")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for paper trading. Install requirements.txt.") from exc

    trading_config = load_or_default_config(args.config)
    if args.symbol:
        trading_config = replace(
            trading_config,
            symbol=args.symbol,
            execution=replace(trading_config.execution, require_symbol=args.symbol),
        )
    if trading_config.execution.allow_order_send:
        message = (
            f"{Path(__file__).name} refuses to run with execution.allow_order_send: true. "
            "Use the demo config or set execution.allow_order_send: false."
        )
        logger.error(message)
        print(message, file=sys.stderr)
        return 2

    try:
        with MT5Client(build_connection_config(args, trading_config.symbol)) as client:
            rates = client.copy_rates_from_pos(
                trading_config.symbol,
                args.timeframe,
                args.bars,
                start_pos=args.start_pos,
            )
            bars = pd.DataFrame(rates)
            if bars.empty:
                raise RuntimeError("MT5 returned no bars")
            bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)

            signal = BaselineSignalGenerator(build_signal_config(args)).generate(bars, trading_config.symbol)
            executor = OrderExecutor(client, trading_config, logger)
            result = executor.execute_signal(signal)

            symbol_info = client.get_symbol_info(trading_config.symbol)
            tick = client.get_symbol_tick(trading_config.symbol)
            account = client.get_account_info()
            positions = client.get_open_positions(trading_config.symbol)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    record = build_record(
        args=args,
        config=trading_config,
        signal=signal,
        result=result,
        bars=bars,
        symbol_info=symbol_info.raw,
        tick=tick.raw,
        account=account.raw,
        open_positions_count=len(positions),
    )
    append_jsonl(Path(args.journal), record)
    logger.info("Wrote paper journal event to %s", args.journal)

    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True, default=str))
    else:
        print_summary(record)
    return 0


def build_record(
    *,
    args: argparse.Namespace,
    config: TradingConfig,
    signal: TradeSignal,
    result: ExecutionResult,
    bars: Any,
    symbol_info: dict[str, Any],
    tick: dict[str, Any],
    account: dict[str, Any],
    open_positions_count: int,
) -> dict[str, Any]:
    latest_bar = bars.iloc[-1]
    risk_decision = risk_decision_to_dict(result.risk_decision)
    return {
        "project": "xm-gold-ai-trader",
        "mode": "paper",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timeframe": args.timeframe,
        "bars_used": int(len(bars)),
        "latest_closed_bar_time": str(latest_bar["time"]),
        "config": {
            "symbol": config.symbol,
            "execution": asdict(config.execution),
            "risk": asdict(config.risk),
        },
        "account": {
            "login": account.get("login"),
            "server": account.get("server"),
            "trade_mode": account.get("trade_mode"),
            "balance": account.get("balance"),
            "equity": account.get("equity"),
            "currency": account.get("currency"),
        },
        "symbol": compact_symbol_info(symbol_info),
        "tick": {
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "time": tick.get("time"),
        },
        "open_positions_count": open_positions_count,
        "signal": asdict(signal),
        "execution": {
            "status": result.status,
            "side": result.side,
            "volume": result.volume,
            "paper_mode": result.paper_mode,
            "reason_codes": list(result.reason_codes),
            "message": result.message,
            "risk_decision": risk_decision,
        },
        "risk_capacity": risk_capacity(symbol_info, config, result.risk_decision),
    }


def compact_symbol_info(symbol_info: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "description",
        "path",
        "digits",
        "point",
        "spread",
        "trade_tick_size",
        "trade_tick_value",
        "trade_contract_size",
        "volume_min",
        "volume_max",
        "volume_step",
        "trade_stops_level",
        "trade_freeze_level",
        "trade_mode",
    )
    return {key: symbol_info.get(key) for key in keys}


def risk_decision_to_dict(decision: RiskDecision | None) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "allowed": decision.allowed,
        "volume": decision.volume,
        "reason_codes": list(decision.reason_codes),
        "reasons": list(decision.reasons),
        "risk_amount": decision.risk_amount,
        "risk_per_lot": decision.risk_per_lot,
        "stop_distance_points": decision.stop_distance_points,
        "take_profit_distance_points": decision.take_profit_distance_points,
    }


def risk_capacity(
    symbol_info: dict[str, Any],
    config: TradingConfig,
    decision: RiskDecision | None,
) -> dict[str, Any] | None:
    if decision is None or decision.risk_per_lot <= 0:
        return None

    spec = SymbolSpec.from_mt5(symbol_info)
    min_lot_risk_amount = spec.volume_min * decision.risk_per_lot
    minimum_equity_for_min_lot = min_lot_risk_amount / (config.risk.risk_per_trade_pct / 100.0)
    return {
        "volume_min": spec.volume_min,
        "risk_per_lot": decision.risk_per_lot,
        "risk_for_min_lot": min_lot_risk_amount,
        "risk_per_trade_pct": config.risk.risk_per_trade_pct,
        "minimum_equity_for_min_lot": minimum_equity_for_min_lot,
    }


def print_summary(record: dict[str, Any]) -> None:
    signal = record["signal"]
    execution = record["execution"]
    risk = execution["risk_decision"]
    print("xm-gold-ai-trader paper run")
    print(f"symbol: {record['symbol']['name']} | timeframe: {record['timeframe']}")
    print(f"account equity: {record['account']['equity']} {record['account']['currency']}")
    print(f"signal: {signal['side']} | confidence: {signal['confidence']} | reason: {signal['reason']}")
    print(f"execution: {execution['status']} | volume: {execution['volume']} | {execution['message']}")
    if execution["reason_codes"]:
        print(f"execution reason codes: {', '.join(execution['reason_codes'])}")
    if risk and risk["reasons"]:
        print(f"risk reasons: {'; '.join(risk['reasons'])}")
    if record["risk_capacity"]:
        capacity = record["risk_capacity"]
        print(
            "minimum equity for broker min lot at this stop: "
            f"{capacity['minimum_equity_for_min_lot']:.2f}"
        )


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")


def load_or_default_config(path: str) -> TradingConfig:
    config_path = Path(path)
    if config_path.exists():
        return load_trading_config(config_path)
    return TradingConfig()


def build_signal_config(args: argparse.Namespace) -> BaselineSignalConfig:
    return BaselineSignalConfig(
        fast_sma=args.fast_sma,
        slow_sma=args.slow_sma,
        atr_period=args.atr_period,
        atr_stop_multiplier=args.atr_stop_multiplier,
        reward_risk_ratio=args.reward_risk_ratio,
    )


def build_connection_config(args: argparse.Namespace, symbol: str) -> MT5ConnectionConfig:
    return MT5ConnectionConfig(
        symbol=symbol,
        terminal_path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
        timeout_ms=args.timeout_ms,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one safe paper-trading evaluation against XM MT5.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--bars", type=int, default=250)
    parser.add_argument("--start-pos", type=int, default=1, help="MT5 bar offset; 1 uses the latest closed bar.")
    parser.add_argument("--journal", default="data/paper_trades.jsonl")
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
    parser.add_argument("--json", action="store_true", help="Print the full paper journal event.")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
