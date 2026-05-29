from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_order_check import build_connection_config, load_or_default_config, result_to_dict
from scripts.reconcile_demo_journal import (
    DEFAULT_JOURNAL_DIR,
    JOURNAL_SCHEMA_VERSION,
    SEVERITY_FAIL,
    SEVERITY_WARNING,
    JournalEntry,
    is_pre_confirmation_block,
    load_journal_entries,
    reconcile_entries,
)
from src.broker.execution_safety import position_matches
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.logging_config import configure_logging


ORDER_SEND_SUCCESS_RETCODES = {0, 10008, 10009}
REASON_ORDER_SEND_RETCODE_NOT_OK = "ORDER_SEND_RETCODE_NOT_OK"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="demo_lifecycle_report")
    config = load_or_default_config(args.config)
    entries = load_journal_entries(Path(args.journal_dir))
    report = summarize_demo_lifecycle(
        entries=entries,
        journal_dir=Path(args.journal_dir),
        expected_symbol=config.symbol,
        project_magic=config.magic_number,
    )
    report["config"] = {
        "symbol": config.symbol,
        "magic_number": config.magic_number,
        "execution": {
            "allow_order_send": config.execution.allow_order_send,
            "require_demo_account": config.execution.require_demo_account,
            "require_symbol": config.execution.require_symbol,
            "max_orders_per_day": config.execution.max_orders_per_day,
            "max_positions": config.execution.max_positions,
            "emergency_stop": config.execution.emergency_stop,
        },
    }

    if args.skip_mt5:
        report["open_matching_positions"] = []
        report["open_positions_error"] = "skipped by --skip-mt5"
    else:
        try:
            with MT5Client(build_connection_config(args, config.symbol)) as client:
                report["open_matching_positions"] = list_open_matching_positions(client, config)
                report["open_positions_error"] = None
        except MT5ClientError as exc:
            logger.error("%s", exc)
            report["open_matching_positions"] = []
            report["open_positions_error"] = str(exc)

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


def summarize_demo_lifecycle(
    *,
    entries: list[JournalEntry],
    journal_dir: Path,
    expected_symbol: str = "GOLD_",
    project_magic: int = 26052601,
) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    malformed_details: list[dict[str, str]] = []
    sent_orders = 0
    order_send_attempts = 0
    rejected_order_sends = 0
    blocked_attempts = 0
    parsed_entries = 0
    legacy_paths: set[str] = set()
    pre_confirmation_blocks = 0

    for entry in entries:
        if entry.payload is None:
            malformed_details.append({"path": str(entry.path), "error": entry.parse_error or "unknown parse error"})
            continue
        payload = entry.payload
        parsed_entries += 1
        if payload.get("journal_schema_version") is None:
            legacy_paths.add(str(entry.path))
        if is_pre_confirmation_block(payload):
            pre_confirmation_blocks += 1
        if order_send_attempted(payload):
            order_send_attempts += 1
        if order_send_accepted(payload):
            sent_orders += 1
        if order_send_rejected(payload):
            rejected_order_sends += 1
        if payload.get("final_decision") == "BLOCK":
            blocked_attempts += 1
        for code in payload.get("reason_codes") or []:
            reason_counter[str(code)] += 1

    audit_findings = reconcile_entries(entries=entries, expected_symbol=expected_symbol, project_magic=project_magic)
    failed_paths = {str(item["path"]) for item in audit_findings if item["severity"] == SEVERITY_FAIL}
    warning_paths = {str(item["path"]) for item in audit_findings if item["severity"] == SEVERITY_WARNING}

    return {
        "project": "xm-gold-ai-trader",
        "mode": "demo_lifecycle_report",
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "orders_sent": 0,
        "journal_dir": str(journal_dir),
        "journals_total": len(entries),
        "valid_journals": parsed_entries - len(failed_paths),
        "legacy_journals": len(legacy_paths),
        "malformed_journals": len(malformed_details),
        "failed_audit_journals": len(failed_paths),
        "warning_journals": len(warning_paths),
        "malformed_journal_details": malformed_details,
        "audit_findings": audit_findings,
        "sent_orders": sent_orders,
        "order_send_attempts": order_send_attempts,
        "rejected_order_sends": rejected_order_sends,
        "blocked_attempts": blocked_attempts,
        "pre_confirmation_blocks": pre_confirmation_blocks,
        "reason_codes": sorted(reason_counter),
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "open_matching_positions": [],
        "open_positions_error": None,
    }


def order_send_attempted(payload: Mapping[str, Any]) -> bool:
    attempts = _int_or_none(payload.get("order_send_attempts"))
    if attempts is not None and attempts > 0:
        return True
    accepted = _int_or_none(payload.get("orders_accepted"))
    if accepted is not None and accepted > 0:
        return True
    sent = _int_or_none(payload.get("orders_sent"))
    if sent is not None and sent > 0:
        return True
    return isinstance(payload.get("order_send_result"), Mapping)


def order_send_accepted(payload: Mapping[str, Any]) -> bool:
    if order_send_rejected(payload):
        return False
    if _int_or_none(payload.get("orders_accepted")) == 1:
        return True
    result = payload.get("order_send_result")
    if isinstance(result, Mapping) and retcode_is_success(result.get("retcode")) and result_has_ticket(result):
        return True
    if _int_or_none(payload.get("orders_sent")) == 1:
        return True
    return False


def order_send_rejected(payload: Mapping[str, Any]) -> bool:
    result = payload.get("order_send_result")
    if not isinstance(result, Mapping):
        return False
    retcode = _int_or_none(result.get("retcode"))
    return retcode is not None and retcode not in ORDER_SEND_SUCCESS_RETCODES


def retcode_is_success(value: Any) -> bool:
    retcode = _int_or_none(value)
    return retcode is not None and retcode in ORDER_SEND_SUCCESS_RETCODES


def result_has_ticket(result: Mapping[str, Any]) -> bool:
    return any((_int_or_none(result.get(field)) or 0) > 0 for field in ("order", "deal", "ticket"))


def list_open_matching_positions(client: Any, config: Any) -> list[dict[str, Any] | None]:
    positions = client.get_open_positions(config.symbol)
    return [
        result_to_dict(position)
        for position in positions
        if position_matches(position, symbol=config.execution.require_symbol, magic=config.magic_number)
    ]


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize demo order journals and current matching positions.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--config", default="config/xm_gold_ai_trader.demo_order_once.yaml")
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--skip-mt5", action="store_true", help="Only summarize journals; do not query open positions.")
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
