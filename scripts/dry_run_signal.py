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
from src.broker.order_executor import TradingConfig, load_trading_config
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging
from src.strategy.baseline_signal import BaselineSignalConfig, BaselineSignalGenerator, TradeSignal
from src.strategy.risk_manager import AccountState, RiskDecision, RiskManager, TradeRiskRequest, spread_points_from_prices


REASON_NO_ACTIONABLE_SIGNAL = "NO_ACTIONABLE_SIGNAL"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="dry_run_signal")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for dry-run signal checks. Install requirements.txt.") from exc

    config = load_or_default_config(args.config)
    if args.symbol:
        config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))
    if config.execution.allow_order_send:
        message = "ALLOW_ORDER_SEND_TRUE: dry_run_signal requires execution.allow_order_send: false"
        logger.error(message)
        print(message, file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    try:
        with MT5Client(build_connection_config(args, config.symbol)) as client:
            rates = client.copy_rates_from_pos(config.symbol, args.timeframe, args.bars, start_pos=args.start_pos)
            bars = pd.DataFrame(rates)
            if bars.empty:
                raise RuntimeError("MT5 returned no bars")
            bars["time"] = pd.to_datetime(bars["time"], unit="s", utc=True)

            symbol_info = client.get_symbol_info(config.symbol)
            tick = client.get_symbol_tick(config.symbol)
            account = client.get_account_info()
            positions = client.get_open_positions(config.symbol)
            daily_pnl = client.get_daily_realized_pnl(config.symbol)
            signal = BaselineSignalGenerator(build_signal_config(args)).generate(bars, config.symbol)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    current_spread = spread_points_from_prices(tick.bid, tick.ask, symbol_info.point)
    risk_decision = assess_signal(
        config=config,
        signal=signal,
        symbol_info=symbol_info.raw,
        account=account.raw,
        daily_pnl=daily_pnl,
        current_spread=current_spread,
        positions=positions,
    )
    decision, reason_codes, reasons = final_decision(signal, risk_decision)
    payload = build_payload(
        args=args,
        config=config,
        signal=signal,
        risk_decision=risk_decision,
        final=decision,
        reason_codes=reason_codes,
        reasons=reasons,
        bars=bars,
        symbol_info=symbol_info.raw,
        tick=tick.raw,
        account=account.raw,
        current_spread=current_spread,
        open_positions_count=len(positions),
    )

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print_summary(payload)
    return event_exit_code(payload)


def assess_signal(
    *,
    config: TradingConfig,
    signal: TradeSignal,
    symbol_info: dict[str, Any],
    account: dict[str, Any],
    daily_pnl: float,
    current_spread: float,
    positions: list[Any],
) -> RiskDecision | None:
    if not signal.is_actionable:
        return None
    return RiskManager(config.risk).assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info,
            account=AccountState(
                balance=float(account["balance"]),
                equity=float(account["equity"]),
                daily_realized_pnl=daily_pnl,
            ),
            side=signal.side,
            entry_price=float(signal.entry_price),
            stop_loss_price=float(signal.stop_loss_price),
            take_profit_price=signal.take_profit_price,
            current_spread_points=current_spread,
            open_positions=positions,
        )
    )


def final_decision(signal: TradeSignal, risk_decision: RiskDecision | None) -> tuple[str, list[str], list[str]]:
    if not signal.is_actionable:
        return "BLOCK", [REASON_NO_ACTIONABLE_SIGNAL], [f"{REASON_NO_ACTIONABLE_SIGNAL}: {signal.reason}"]
    if risk_decision is None:
        return "BLOCK", ["RISK_NOT_EVALUATED"], ["RISK_NOT_EVALUATED: no risk decision was produced"]
    if not risk_decision.allowed:
        return "BLOCK", list(risk_decision.reason_codes), list(risk_decision.reasons)
    return "ALLOW", [], []


def build_payload(
    *,
    args: argparse.Namespace,
    config: TradingConfig,
    signal: TradeSignal,
    risk_decision: RiskDecision | None,
    final: str,
    reason_codes: list[str],
    reasons: list[str],
    bars: Any,
    symbol_info: dict[str, Any],
    tick: dict[str, Any],
    account: dict[str, Any],
    current_spread: float,
    open_positions_count: int,
) -> dict[str, Any]:
    latest_bar = bars.iloc[-1]
    proposed_lot = risk_decision.volume if risk_decision else 0.0
    return {
        "project": "xm-gold-ai-trader",
        "mode": "dry_run",
        "orders_sent": 0,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "final_decision": final,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "timeframe": args.timeframe,
        "bars_used": int(len(bars)),
        "latest_closed_bar_time": str(latest_bar["time"]),
        "config": {"symbol": config.symbol, "execution": asdict(config.execution), "risk": asdict(config.risk)},
        "account": {
            "login": account.get("login"),
            "server": account.get("server"),
            "balance": account.get("balance"),
            "equity": account.get("equity"),
            "currency": account.get("currency"),
        },
        "symbol": compact_symbol(symbol_info),
        "tick": {"bid": tick.get("bid"), "ask": tick.get("ask"), "time": tick.get("time")},
        "current_spread_points": current_spread,
        "open_positions_count": open_positions_count,
        "signal": asdict(signal),
        "proposal": {
            "side": signal.side,
            "entry_price": signal.entry_price,
            "stop_loss_price": signal.stop_loss_price,
            "take_profit_price": signal.take_profit_price,
            "lot": proposed_lot,
        },
        "risk_decision": risk_decision_to_dict(risk_decision),
    }


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


def print_summary(payload: dict[str, Any]) -> None:
    proposal = payload["proposal"]
    print("xm-gold-ai-trader dry run")
    print(f"final decision: {payload['final_decision']}")
    if payload["reason_codes"]:
        print(f"reason codes: {', '.join(payload['reason_codes'])}")
    for reason in payload["reasons"]:
        print(f"reason: {reason}")
    print(f"symbol: {payload['symbol']['name']} | timeframe: {payload['timeframe']}")
    print(f"account equity: {payload['account']['equity']} {payload['account']['currency']}")
    print(f"spread points: {payload['current_spread_points']:.1f}")
    print(f"signal: {payload['signal']['side']} | {payload['signal']['reason']}")
    print(
        "proposal: "
        f"side={proposal['side']} entry={proposal['entry_price']} "
        f"sl={proposal['stop_loss_price']} tp={proposal['take_profit_price']} lot={proposal['lot']}"
    )
    print("orders_sent: 0")


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "description",
        "path",
        "point",
        "spread",
        "trade_tick_size",
        "trade_tick_value",
        "volume_min",
        "volume_max",
        "volume_step",
        "trade_stops_level",
        "trade_mode",
    )
    return {key: symbol.get(key) for key in keys}


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
    parser = argparse.ArgumentParser(description="Compute a baseline signal and risk decision without order_send.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--bars", type=int, default=250)
    parser.add_argument("--start-pos", type=int, default=1, help="MT5 bar offset; 1 uses the latest closed bar.")
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
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
