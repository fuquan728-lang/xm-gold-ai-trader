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

from scripts.preflight_order_check import build_connection_config, load_or_default_config, result_to_dict
from src.broker.execution_safety import (
    REASON_EMERGENCY_STOP_FILE_PRESENT,
    REASON_NO_MATCHING_POSITIONS,
    REASON_ORDER_CHECK_FAILED,
    evaluate_execution_safety,
    order_check_passed,
    position_matches,
)
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.broker.order_executor import TradingConfig
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging
from src.runtime.lock import DEFAULT_EMERGENCY_STOP_PATH, emergency_stop_file_decision


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="close_demo_positions")
    config = load_or_default_config(args.config)
    if args.symbol:
        config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))

    try:
        emergency_decision = emergency_stop_file_decision(DEFAULT_EMERGENCY_STOP_PATH)
        if not emergency_decision.acquired:
            event = close_positions_base_event(config=config, account=None, positions=[], targets=[])
            event = block_event(event, emergency_decision.reason_codes, emergency_decision.reasons)
        else:
            with MT5Client(build_connection_config(args, config.symbol)) as client:
                event = close_matching_demo_positions(client, config)
    except MT5ClientError as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    append_jsonl(Path(args.journal), event)
    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def close_matching_demo_positions(
    client: Any,
    config: TradingConfig,
    *,
    emergency_stop_path: Path = DEFAULT_EMERGENCY_STOP_PATH,
) -> dict[str, Any]:
    account = client.get_account_info()
    positions = client.get_open_positions(config.symbol)
    targets = [
        position
        for position in positions
        if position_matches(position, symbol=config.execution.require_symbol, magic=config.magic_number)
    ]
    event = close_positions_base_event(config=config, account=account, positions=positions, targets=targets)

    emergency_decision = emergency_stop_file_decision(emergency_stop_path)
    if not emergency_decision.acquired:
        return block_event(event, emergency_decision.reason_codes, emergency_decision.reasons)

    execution_decision = evaluate_execution_safety(
        config=config.execution,
        account_info=account.raw if account is not None else None,
        symbol=config.symbol,
        open_positions=(),
        orders_today=0,
        project_magic=config.magic_number,
        require_order_send_permission=True,
    )
    if not execution_decision.allowed:
        return block_event(event, execution_decision.reason_codes, execution_decision.reasons)

    if not targets:
        event["final_decision"] = "NO_MATCH"
        event["reason_codes"] = [REASON_NO_MATCHING_POSITIONS]
        event["reasons"] = [f"{REASON_NO_MATCHING_POSITIONS}: no matching {config.symbol} positions with project magic"]
        return event

    for position in targets:
        request = client.build_close_position_request(
            position=position,
            deviation_points=config.deviation_points,
            magic_number=config.magic_number,
            comment=f"{config.order_comment}-close",
        )
        check_result = client.order_check(request)
        attempt = {
            "position": result_to_dict(position),
            "request": request,
            "order_check_result": result_to_dict(check_result),
            "order_send_result": None,
            "sent": False,
            "reason_codes": [],
            "reasons": [],
        }
        if not order_check_passed(check_result):
            attempt["reason_codes"] = [REASON_ORDER_CHECK_FAILED]
            attempt["reasons"] = [f"{REASON_ORDER_CHECK_FAILED}: order_check did not pass"]
            event["close_attempts"].append(attempt)
            continue
        send_result = client.order_send_checked(request, check_result)
        attempt["order_send_result"] = result_to_dict(send_result)
        attempt["sent"] = True
        event["orders_sent"] += 1
        event["close_attempts"].append(attempt)

    if event["orders_sent"] > 0:
        event["final_decision"] = "CLOSED"
    else:
        event["final_decision"] = "BLOCK"
        event["reason_codes"] = [REASON_ORDER_CHECK_FAILED]
        event["reasons"] = [f"{REASON_ORDER_CHECK_FAILED}: all close order_check calls failed"]
    return event


def close_positions_base_event(
    *,
    config: TradingConfig,
    account: Any,
    positions: list[Any],
    targets: list[Any],
) -> dict[str, Any]:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "close_demo_positions",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": [],
        "reasons": [],
        "config": {"symbol": config.symbol, "execution": asdict(config.execution), "risk": asdict(config.risk)},
        "account": result_to_dict(account),
        "positions_seen": [result_to_dict(position) for position in positions],
        "target_positions": [result_to_dict(position) for position in targets],
        "close_attempts": [],
    }


def block_event(event: dict[str, Any], codes: tuple[str, ...], reasons: tuple[str, ...]) -> dict[str, Any]:
    event["final_decision"] = "BLOCK"
    event["reason_codes"] = list(codes)
    event["reasons"] = list(reasons)
    return event


def append_jsonl(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close only matching project demo positions after order_check.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL"))
    parser.add_argument("--journal", default="data/demo_close_positions.jsonl")
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
