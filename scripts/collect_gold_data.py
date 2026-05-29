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
    logger = configure_logging(logger_name="collect_gold_data")

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required for data collection. Install requirements.txt.") from exc

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path.with_suffix(output_path.suffix + ".symbol_info.json")

    try:
        with MT5Client(build_connection_config(args)) as client:
            symbol_info = client.get_symbol_info(args.symbol)
            rates = client.copy_rates_from_pos(args.symbol, args.timeframe, args.bars)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 2

    frame = pd.DataFrame(rates)
    if frame.empty:
        raise RuntimeError("MT5 returned no bars")
    frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
    frame.to_csv(output_path, index=False)

    metadata = {
        "project": "xm-gold-ai-trader",
        "symbol_info_source": f'MetaTrader5.symbol_info("{args.symbol}")',
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "bars": int(len(frame)),
        "output": str(output_path),
        "symbol_info": symbol_info.raw,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding="utf-8")
    logger.info("Wrote %s bars to %s", len(frame), output_path)
    logger.info("Wrote symbol metadata to %s", metadata_path)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GOLD_ OHLCV bars from XM MT5.")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--output", default="data/gold_m15.csv")
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


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
