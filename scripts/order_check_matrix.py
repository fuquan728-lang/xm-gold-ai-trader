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

from scripts.manual_preflight_order_check import (
    DEFAULT_TP_RR,
    compact_account,
    compact_symbol,
    configured_tp_rr,
    manual_preflight_order_check,
)
from scripts.preflight_order_check import build_connection_config, load_or_default_config
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.broker.order_executor import TradingConfig
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging


REASON_NO_ORDER_CHECK_CASE_REACHED = "NO_ORDER_CHECK_CASE_REACHED"
MATRIX_CASES: tuple[tuple[str, float], ...] = (
    ("BUY", 100.0),
    ("BUY", 150.0),
    ("BUY", 200.0),
    ("SELL", 100.0),
    ("SELL", 150.0),
    ("SELL", 200.0),
)


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="order_check_matrix")

    try:
        config = load_or_default_config(args.config)
        if args.symbol:
            config = replace(config, symbol=args.symbol, execution=replace(config.execution, require_symbol=args.symbol))
        tp_rr = args.tp_rr if args.tp_rr is not None else configured_tp_rr(args.config)

        with MT5Client(build_connection_config(args, config.symbol)) as client:
            client.ensure_symbol(config.symbol)
            event = order_check_matrix(client=client, config=config, risk_pct_override=args.risk_pct, tp_rr=tp_rr)
    except (MT5ClientError, OSError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def order_check_matrix(
    *,
    client: Any,
    config: TradingConfig,
    risk_pct_override: float | None = None,
    tp_rr: float = DEFAULT_TP_RR,
    cases: tuple[tuple[str, float], ...] = MATRIX_CASES,
) -> dict[str, Any]:
    account = client.get_account_info()
    symbol_info = client.get_symbol_info(config.symbol)
    case_results: list[dict[str, Any]] = []
    order_check_cases = 0

    for side, stop_points in cases:
        case_event = manual_preflight_order_check(
            client=client,
            config=config,
            side=side,
            risk_pct_override=risk_pct_override,
            stop_points=stop_points,
            tp_rr=tp_rr,
        )
        case = matrix_case(case_event=case_event, side=side, stop_points=stop_points)
        if case["order_check_result"] is not None:
            order_check_cases += 1
        case_results.append(case)

    event = {
        "project": "xm-gold-ai-trader",
        "mode": "order_check_matrix",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": [],
        "reasons": [],
        "config": {"symbol": config.symbol, "execution": asdict(config.execution), "risk": asdict(config.risk)},
        "account": compact_account(account),
        "symbol": compact_symbol(symbol_info),
        "order_check_cases": order_check_cases,
        "cases": case_results,
    }
    return finalize_matrix_event(event)


def matrix_case(*, case_event: dict[str, Any], side: str, stop_points: float) -> dict[str, Any]:
    risk = case_event.get("local_risk_decision") or {}
    return {
        "side": side,
        "stop_points": stop_points,
        "final_decision": case_event.get("final_decision", "BLOCK"),
        "reason_codes": list(case_event.get("reason_codes") or []),
        "reasons": list(case_event.get("reasons") or []),
        "lot": float(risk.get("volume") or 0.0),
        "candidate_order": case_event.get("candidate_order"),
        "local_risk_decision": case_event.get("local_risk_decision"),
        "order_check_result": case_event.get("order_check_result"),
    }


def finalize_matrix_event(event: dict[str, Any]) -> dict[str, Any]:
    cases = list(event["cases"])
    if any(case["final_decision"] == "ALLOW" for case in cases):
        event["final_decision"] = "ALLOW"
        return event

    if int(event.get("order_check_cases", 0)) == 0:
        event["final_decision"] = "BLOCK"
        event["reason_codes"] = [REASON_NO_ORDER_CHECK_CASE_REACHED]
        event["reasons"] = [
            f"{REASON_NO_ORDER_CHECK_CASE_REACHED}: all matrix cases were blocked before order_check",
        ]
        return event

    reason_codes: list[str] = []
    reasons: list[str] = []
    for case in cases:
        if case["order_check_result"] is None:
            continue
        for code in case["reason_codes"]:
            if code not in reason_codes:
                reason_codes.append(code)
        for reason in case["reasons"]:
            if reason not in reasons:
                reasons.append(reason)
    event["final_decision"] = "BLOCK"
    event["reason_codes"] = reason_codes or ["ORDER_CHECK_CASES_BLOCKED"]
    event["reasons"] = reasons or ["ORDER_CHECK_CASES_BLOCKED: all order_check cases were blocked"]
    return event


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a BUY/SELL stop-distance order_check matrix without order_send.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=None, help="Optional override; defaults to the configured symbol.")
    parser.add_argument("--risk-pct", type=_positive_float, default=None)
    parser.add_argument("--tp-rr", type=_positive_float, default=None)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
