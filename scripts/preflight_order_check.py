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

from src.broker.execution_safety import (
    REASON_ORDER_CHECK_FAILED,
    evaluate_execution_safety,
    order_check_passed,
)
from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.broker.order_executor import TradingConfig, load_trading_config
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator, TradeSignal
from src.strategy.risk_manager import AccountState, RiskDecision, RiskManager, TradeRiskRequest, spread_points_from_prices


REASON_NO_ACTIONABLE_SIGNAL = "NO_ACTIONABLE_SIGNAL"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="preflight_order_check")
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for preflight checks. Install requirements.txt.") from exc

    config = load_or_default_config(args.config)
    if args.symbol:
        config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))

    try:
        with MT5Client(build_connection_config(args, config.symbol)) as client:
            rates = client.copy_rates_from_pos(config.symbol, args.timeframe, args.bars, start_pos=args.start_pos)
            bars = pd.DataFrame(rates)
            if bars.empty:
                raise RuntimeError("MT5 returned no bars")
            bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)
            signal = BaselineSignalGenerator(build_signal_config(args)).generate(bars, config.symbol)
            event = preflight_order_check(client, config, signal)
            event["timeframe"] = args.timeframe
            event["bars_used"] = int(len(bars))
            event["latest_closed_bar_time"] = str(bars.iloc[-1]["time"])
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def preflight_order_check(client: Any, config: TradingConfig, signal: TradeSignal) -> dict[str, Any]:
    symbol_info = client.get_symbol_info(config.symbol)
    tick = client.get_symbol_tick(config.symbol)
    account = client.get_account_info()
    positions = client.get_open_positions(config.symbol)
    daily_pnl = client.get_daily_realized_pnl(config.symbol)
    orders_today = get_orders_today(client, config)
    current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)

    event = base_event(config=config, signal=signal, account=account, symbol_info=symbol_info, tick=tick)
    event["orders_today"] = orders_today
    event["open_positions_count"] = len(positions)
    event["current_spread_points"] = current_spread

    execution_decision = evaluate_execution_safety(
        config=config.execution,
        account_info=account.raw if account is not None else None,
        symbol=config.symbol,
        open_positions=positions,
        orders_today=orders_today,
        project_magic=config.magic_number,
        require_order_send_permission=False,
    )
    if not execution_decision.allowed:
        return block_event(event, execution_decision.reason_codes, execution_decision.reasons)

    if not signal.is_actionable:
        return block_event(
            event,
            (REASON_NO_ACTIONABLE_SIGNAL,),
            (f"{REASON_NO_ACTIONABLE_SIGNAL}: {signal.reason}",),
        )

    risk_decision = RiskManager(config.risk).assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info.raw,
            account=AccountState(
                balance=account.balance,
                equity=account.equity,
                daily_realized_pnl=daily_pnl,
            ),
            side=signal.side,
            entry_price=tick.ask if signal.side == "BUY" else tick.bid,
            stop_loss_price=float(signal.stop_loss_price),
            take_profit_price=signal.take_profit_price,
            current_spread_points=current_spread,
            open_positions=positions,
        )
    )
    event["risk_decision"] = risk_decision_to_dict(risk_decision)
    if not risk_decision.allowed:
        return block_event(event, risk_decision.reason_codes, risk_decision.reasons)

    request = client.build_market_order_request(
        symbol=config.symbol,
        side=signal.side,
        volume=risk_decision.volume,
        stop_loss=float(signal.stop_loss_price),
        take_profit=signal.take_profit_price,
        deviation_points=config.deviation_points,
        magic_number=config.magic_number,
        comment=config.order_comment,
    )
    event["order_request"] = request
    order_check_result = client.order_check(request)
    event["order_check_result"] = result_to_dict(order_check_result)
    if not order_check_passed(order_check_result):
        return block_event(
            event,
            (REASON_ORDER_CHECK_FAILED,),
            (f"{REASON_ORDER_CHECK_FAILED}: order_check did not pass",),
        )

    event["final_decision"] = "ALLOW"
    return event


def base_event(config: TradingConfig, signal: TradeSignal, account: Any, symbol_info: Any, tick: Any) -> dict[str, Any]:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "preflight_order_check",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": [],
        "reasons": [],
        "config": {"symbol": config.symbol, "execution": asdict(config.execution), "risk": asdict(config.risk)},
        "account": result_to_dict(account),
        "symbol": compact_symbol(symbol_info.raw),
        "tick": result_to_dict(tick),
        "signal": asdict(signal),
        "risk_decision": None,
        "order_request": None,
        "order_check_result": None,
    }


def block_event(event: dict[str, Any], codes: tuple[str, ...], reasons: tuple[str, ...]) -> dict[str, Any]:
    event["final_decision"] = "BLOCK"
    event["reason_codes"] = list(codes)
    event["reasons"] = list(reasons)
    return event


def risk_decision_to_dict(decision: RiskDecision) -> dict[str, Any]:
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


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    keys = ("name", "path", "point", "spread", "trade_tick_size", "trade_tick_value", "volume_min", "volume_step")
    return {key: symbol.get(key) for key in keys}


def result_to_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    if hasattr(value, "raw"):
        return getattr(value, "raw")
    if isinstance(value, dict):
        return value
    return dict(getattr(value, "__dict__", {}))


def get_orders_today(client: Any, config: TradingConfig) -> int:
    if hasattr(client, "get_daily_order_count"):
        return int(client.get_daily_order_count(config.symbol, config.magic_number))
    return 0


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
    parser = argparse.ArgumentParser(description="Run order_check preflight only; never calls order_send.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--bars", type=int, default=250)
    parser.add_argument("--start-pos", type=int, default=1)
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
    parser.add_argument("--json", action="store_true", help="Accepted for verifier compatibility; output is always JSON.")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
