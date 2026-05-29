from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.broker.mt5_client import MT5Client, MT5ClientError, MT5ConnectionConfig
from src.logging_config import configure_logging


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="inspect_symbol")

    config = build_connection_config(args)
    try:
        with MT5Client(config) as client:
            account = client.get_account_info()
            account_payload = {
                "login": account.login,
                "trade_mode": account.trade_mode,
                "server": account.server,
                "currency": account.currency,
                "balance": account.balance,
                "equity": account.equity,
            }
            if args.discover:
                payload = {
                    "project": "xm-gold-ai-trader",
                    "account": account_payload,
                    "patterns": args.match,
                    "candidates": client.discover_symbols(args.match),
                }
            else:
                symbol = client.get_symbol_info(args.symbol)
                payload = {
                    "project": "xm-gold-ai-trader",
                    "symbol_info_source": f'MetaTrader5.symbol_info("{args.symbol}")',
                    "account": account_payload,
                    "symbol": symbol.raw,
                }
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    elif args.discover:
        print("xm-gold-ai-trader symbol discovery")
        print(f"Account: {payload['account']['login']} {payload['account']['server']}")
        if not payload["candidates"]:
            print("No Gold/XAU candidates found. Check the MT5 account/server and Market Watch symbols.")
        for candidate in payload["candidates"]:
            print(
                f"{candidate['name']} | visible={candidate['visible']} | "
                f"spread={candidate['spread']} | path={candidate['path']}"
            )
    else:
        print("xm-gold-ai-trader symbol inspection")
        print(f"Source: MetaTrader5.symbol_info({args.symbol!r})")
        print(f"Account: {payload['account']['login']} {payload['account']['server']}")
        for key in (
            "name",
            "description",
            "path",
            "digits",
            "point",
            "trade_tick_size",
            "trade_tick_value",
            "trade_contract_size",
            "volume_min",
            "volume_max",
            "volume_step",
            "trade_stops_level",
            "trade_freeze_level",
            "spread",
            "spread_float",
            "currency_base",
            "currency_profit",
            "currency_margin",
            "trade_mode",
            "filling_mode",
            "order_mode",
        ):
            print(f"{key}: {payload['symbol'].get(key)}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect XM MT5 symbol_info for GOLD_.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--discover", action="store_true", help="List Gold/XAU-like symbols available in MT5.")
    parser.add_argument(
        "--match",
        action="append",
        default=None,
        help="MT5 symbols_get pattern for discovery. Can be repeated, for example --match *GOLD* --match *XAU*.",
    )
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true", help="Print full JSON payload.")
    return parser.parse_args()


def build_connection_config(args: argparse.Namespace) -> MT5ConnectionConfig:
    return MT5ConnectionConfig(
        symbol=args.symbol,
        terminal_path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
        timeout_ms=args.timeout_ms,
        validate_symbol_on_connect=not args.discover,
    )


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
