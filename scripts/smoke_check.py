from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.broker.order_executor import TradingConfig, load_trading_config
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="smoke_check")
    config = load_or_default_config(args.config)
    if args.symbol:
        config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))

    validation_errors = validate_config(config)
    if validation_errors:
        payload = {
            "project": "xm-gold-ai-trader",
            "status": "CONFIG_INVALID",
            "orders_sent": 0,
            "errors": validation_errors,
        }
        print_payload(payload, args.json)
        return EXIT_RUNTIME_FAILURE

    try:
        with MT5Client(build_connection_config(args, config.symbol)) as client:
            symbol = client.ensure_symbol(config.symbol)
            account = client.get_account_info()
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    payload = {
        "project": "xm-gold-ai-trader",
        "status": "OK",
        "orders_sent": 0,
        "config": {
            "symbol": config.symbol,
            "execution": asdict(config.execution),
            "risk": asdict(config.risk),
        },
        "account": compact_account(account.raw),
        "symbol": compact_symbol(symbol.raw),
        "checks": [
            "connected_to_mt5",
            "selected_symbol",
            "read_account_info",
            "read_symbol_info",
            "validated_config",
            "no_order_send_called",
        ],
    }
    print_payload(payload, args.json)
    return event_exit_code(payload)


def validate_config(config: TradingConfig) -> list[str]:
    errors: list[str] = []
    if config.execution.allow_order_send:
        errors.append("ALLOW_ORDER_SEND_TRUE: smoke_check requires execution.allow_order_send: false")
    if config.risk.allow_martingale:
        errors.append("MARTINGALE_ENABLED: martingale is prohibited")
    if config.risk.allow_grid:
        errors.append("GRID_ENABLED: grid trading is prohibited")
    if config.risk.allow_lot_increase_after_loss:
        errors.append("LOT_INCREASE_AFTER_LOSS_ENABLED: automatic lot increase after loss is prohibited")
    return errors


def print_payload(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    print("xm-gold-ai-trader smoke check")
    print(f"status: {payload['status']}")
    if payload["status"] != "OK":
        for error in payload["errors"]:
            print(f"error: {error}")
        return
    print(f"account: {payload['account']['login']} {payload['account']['server']}")
    print(f"equity: {payload['account']['equity']} {payload['account']['currency']}")
    print(f"symbol: {payload['symbol']['name']} {payload['symbol']['path']}")
    print(f"spread points: {payload['symbol']['spread']}")
    print(f"volume min/max/step: {payload['symbol']['volume_min']} / {payload['symbol']['volume_max']} / {payload['symbol']['volume_step']}")
    print(f"allow_order_send: {payload['config']['execution']['allow_order_send']}")
    print("orders_sent: 0")


def compact_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "login": account.get("login"),
        "server": account.get("server"),
        "trade_mode": account.get("trade_mode"),
        "balance": account.get("balance"),
        "equity": account.get("equity"),
        "currency": account.get("currency"),
    }


def compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "description",
        "path",
        "digits",
        "point",
        "spread",
        "spread_float",
        "trade_contract_size",
        "trade_tick_size",
        "trade_tick_value",
        "volume_min",
        "volume_max",
        "volume_step",
        "trade_stops_level",
        "trade_freeze_level",
        "trade_mode",
    )
    return {key: symbol.get(key) for key in keys}


def load_or_default_config(path: str) -> TradingConfig:
    config_path = Path(path)
    if config_path.exists():
        return load_trading_config(config_path)
    return TradingConfig()


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
    parser = argparse.ArgumentParser(description="Verify MT5, account, symbol, and config without placing orders.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
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
