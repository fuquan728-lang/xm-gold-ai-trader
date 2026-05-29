from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.demo_lifecycle_report import order_send_accepted, order_send_rejected
from scripts.preflight_order_check import build_connection_config, load_or_default_config, result_to_dict
from scripts.reconcile_demo_journal import DEFAULT_JOURNAL_DIR, JournalEntry, load_journal_entries
from src.broker.execution_safety import position_matches
from src.broker.mt5_client import MT5Client, MT5ClientError
from src.cli_contract import EXIT_RUNTIME_FAILURE, event_exit_code
from src.logging_config import configure_logging


PROJECT = "xm-gold-ai-trader"
MODE = "reconcile_mt5_history"

CLASS_OPEN_POSITION_MATCHED = "OPEN_POSITION_MATCHED"
CLASS_CLOSED_IN_HISTORY = "CLOSED_IN_HISTORY"
CLASS_SENT_BUT_NOT_FOUND = "SENT_BUT_NOT_FOUND"
CLASS_HISTORY_QUERY_FAILED = "HISTORY_QUERY_FAILED"
CLASS_INVALID_SENT_JOURNAL = "INVALID_SENT_JOURNAL"

REASON_SENT_BUT_NOT_FOUND = CLASS_SENT_BUT_NOT_FOUND
REASON_HISTORY_QUERY_FAILED = CLASS_HISTORY_QUERY_FAILED
REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING = "SENT_JOURNAL_REQUIRED_FIELD_MISSING"


@dataclass(frozen=True, slots=True)
class SentJournal:
    path: Path
    payload: Mapping[str, Any]
    order_id: int | None
    deal_id: int | None
    symbol: str
    magic_number: int
    account: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InvalidSentJournal:
    path: Path
    payload: Mapping[str, Any]
    missing_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SentJournalAudit:
    valid: list[SentJournal]
    invalid: list[InvalidSentJournal]
    rejected: list[JournalEntry]


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="reconcile_mt5_history")
    config = load_or_default_config(args.config)
    entries = load_journal_entries(Path(args.journal_dir))
    audit = prepare_sent_journal_audit(entries)

    try:
        if audit.valid:
            with MT5Client(build_connection_config(args, config.symbol)) as client:
                event = reconcile_mt5_history_entries(
                    entries=entries,
                    client=client,
                    lookback_days=args.lookback_days,
                )
        else:
            event = reconcile_mt5_history_entries(
                entries=entries,
                client=None,
                lookback_days=args.lookback_days,
            )
    except (MT5ClientError, OSError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_FAILURE

    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def reconcile_mt5_history_entries(
    *,
    entries: list[JournalEntry],
    client: Any | None,
    lookback_days: int = 90,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    audit = prepare_sent_journal_audit(entries)
    event = base_event(audit=audit)
    if not audit.valid:
        update_counts_and_decision(event)
        return event
    if client is None:
        return block_history_query_failed(event, audit.valid, "MT5 client is required when sent journals exist")

    try:
        current_positions = query_current_positions(client, audit.valid)
        date_from, date_to = history_window(audit.valid, lookback_days=lookback_days, now_utc=now_utc)
        history_orders = client.get_history_orders(date_from, date_to)
        history_deals = client.get_history_deals(date_from, date_to)
    except Exception as exc:
        return block_history_query_failed(event, audit.valid, str(exc))

    event["current_open_positions"] = [
        result_to_dict(position)
        for position in current_positions
    ]
    event["history_query"] = {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "orders_returned": len(history_orders),
        "deals_returned": len(history_deals),
    }

    for journal in audit.valid:
        match = classify_sent_journal(
            journal=journal,
            current_positions=current_positions,
            history_orders=history_orders,
            history_deals=history_deals,
        )
        event["history_matches"].append(match)

    update_counts_and_decision(event)
    return event


def base_event(*, audit: SentJournalAudit) -> dict[str, Any]:
    return {
        "project": PROJECT,
        "mode": MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "final_decision": "ALLOW",
        "reason_codes": [],
        "reasons": [],
        "sent_journals_checked": len(audit.valid) + len(audit.invalid),
        "invalid_sent_journals": len(audit.invalid),
        "rejected_order_sends": len(audit.rejected),
        "open_positions_matched": 0,
        "closed_in_history": 0,
        "missing_in_history": 0,
        "history_query_failed": 0,
        "current_open_positions": [],
        "history_matches": [invalid_sent_journal_match(item) for item in audit.invalid],
        "history_query": None,
    }


def prepare_sent_journal_audit(entries: Sequence[JournalEntry]) -> SentJournalAudit:
    valid: list[SentJournal] = []
    invalid: list[InvalidSentJournal] = []
    rejected: list[JournalEntry] = []
    for entry in entries:
        payload = entry.payload
        if not isinstance(payload, Mapping) or not is_candidate_sent_payload(payload):
            continue
        if order_send_rejected(payload):
            rejected.append(entry)
            continue
        journal, missing_fields = extract_sent_journal(entry)
        if journal is None:
            invalid.append(
                InvalidSentJournal(
                    path=entry.path,
                    payload=payload,
                    missing_fields=tuple(missing_fields),
                )
            )
            continue
        valid.append(journal)
    return SentJournalAudit(valid=valid, invalid=invalid, rejected=rejected)


def accepted_sent_journals(entries: Sequence[JournalEntry]) -> list[SentJournal]:
    return prepare_sent_journal_audit(entries).valid


def rejected_send_journals(entries: Sequence[JournalEntry]) -> list[JournalEntry]:
    return prepare_sent_journal_audit(entries).rejected


def is_candidate_sent_payload(payload: Mapping[str, Any]) -> bool:
    if payload.get("final_decision") == "SENT":
        return True
    if _int_or_none(payload.get("orders_sent")) == 1:
        return True
    if _int_or_none(payload.get("orders_accepted")) == 1:
        return True
    return order_send_accepted(payload)


def extract_sent_journal(entry: JournalEntry) -> tuple[SentJournal | None, list[str]]:
    payload = entry.payload
    if not isinstance(payload, Mapping):
        return None, ["journal"]
    order_send_result = payload.get("order_send_result")
    if not isinstance(order_send_result, Mapping):
        order_send_result = {}
    symbol = first_text(
        _nested(payload, "candidate_order", "symbol"),
        _nested(payload, "symbol", "name"),
    )
    magic_number = first_int(_nested(payload, "config", "magic_number"))
    order_id = first_int(order_send_result.get("order"), order_send_result.get("ticket"))
    deal_id = first_int(order_send_result.get("deal"))
    missing_fields = missing_sent_journal_fields(
        payload=payload,
        symbol=symbol,
        magic_number=magic_number,
        order_send_result=order_send_result,
        order_id=order_id,
        deal_id=deal_id,
    )
    if missing_fields:
        return None, missing_fields
    account = {
        "login": _nested(payload, "account", "login"),
        "server": _nested(payload, "account", "server"),
    }
    return SentJournal(
        path=entry.path,
        payload=payload,
        order_id=order_id,
        deal_id=deal_id,
        symbol=symbol,
        magic_number=magic_number,
        account=account,
    ), []


def missing_sent_journal_fields(
    *,
    payload: Mapping[str, Any],
    symbol: str,
    magic_number: int | None,
    order_send_result: Mapping[str, Any],
    order_id: int | None,
    deal_id: int | None,
) -> list[str]:
    missing: list[str] = []
    if parse_timestamp(payload.get("timestamp_utc")) is None:
        missing.append("timestamp_utc")
    if _nested(payload, "account", "login") is None:
        missing.append("account.login")
    if not _nested(payload, "account", "server"):
        missing.append("account.server")
    if not symbol:
        missing.append("candidate_order.symbol_or_symbol.name")
    if magic_number is None:
        missing.append("config.magic_number")
    if not isinstance(payload.get("order_send_result"), Mapping):
        missing.append("order_send_result")
    if _int_or_none(order_send_result.get("retcode")) is None:
        missing.append("order_send_result.retcode")
    if order_id is None and deal_id is None:
        missing.append("order_send_result.order_or_deal")
    return missing


def invalid_sent_journal_match(journal: InvalidSentJournal) -> dict[str, Any]:
    payload = journal.payload
    order_send_result = payload.get("order_send_result")
    if not isinstance(order_send_result, Mapping):
        order_send_result = {}
    return {
        "journal_path": str(journal.path),
        "classification": CLASS_INVALID_SENT_JOURNAL,
        "reason_code": REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING,
        "missing_fields": list(journal.missing_fields),
        "symbol": first_text(
            _nested(payload, "candidate_order", "symbol"),
            _nested(payload, "symbol", "name"),
            _nested(payload, "config", "symbol"),
        ),
        "magic_number": first_int(
            _nested(payload, "config", "magic_number"),
            _nested(payload, "candidate_order", "mt5_request", "magic"),
        ),
        "account": {
            "login": _nested(payload, "account", "login"),
            "server": _nested(payload, "account", "server"),
        },
        "order": first_int(order_send_result.get("order"), order_send_result.get("ticket")),
        "deal": first_int(order_send_result.get("deal")),
        "matched_position": None,
        "matched_order": None,
        "matched_deal": None,
    }


def query_current_positions(client: Any, sent_journals: Sequence[SentJournal]) -> list[Any]:
    positions: list[Any] = []
    seen_keys: set[tuple[str, int | None, int | None]] = set()
    for symbol in sorted({journal.symbol for journal in sent_journals}):
        for position in client.get_open_positions(symbol):
            data = result_to_dict(position) or {}
            key = (
                str(data.get("symbol") or getattr(position, "symbol", "")),
                _int_or_none(data.get("magic") if isinstance(data, Mapping) else None) or _int_or_none(getattr(position, "magic", None)),
                _int_or_none(data.get("ticket") if isinstance(data, Mapping) else None) or _int_or_none(getattr(position, "ticket", None)),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if any(position_matches(position, symbol=journal.symbol, magic=journal.magic_number) for journal in sent_journals):
                positions.append(position)
    return positions


def history_window(
    sent_journals: Sequence[SentJournal],
    *,
    lookback_days: int,
    now_utc: datetime | None = None,
) -> tuple[datetime, datetime]:
    now = now_utc or datetime.now(timezone.utc)
    parsed_times = [
        parsed
        for parsed in (parse_timestamp(_nested(journal.payload, "timestamp_utc")) for journal in sent_journals)
        if parsed is not None
    ]
    if parsed_times:
        date_from = min(parsed_times) - timedelta(days=1)
    else:
        date_from = now - timedelta(days=lookback_days)
    return date_from, now + timedelta(days=1)


def classify_sent_journal(
    *,
    journal: SentJournal,
    current_positions: Sequence[Any],
    history_orders: Sequence[Any],
    history_deals: Sequence[Any],
) -> dict[str, Any]:
    matched_position = first_matching_position(journal, current_positions)
    if matched_position is not None:
        classification = CLASS_OPEN_POSITION_MATCHED
        matched_order = None
        matched_deal = None
    else:
        matched_order = first_matching_order(journal, history_orders)
        matched_deal = first_matching_deal(journal, history_deals)
        classification = CLASS_CLOSED_IN_HISTORY if matched_order is not None or matched_deal is not None else CLASS_SENT_BUT_NOT_FOUND

    return {
        "journal_path": str(journal.path),
        "classification": classification,
        "symbol": journal.symbol,
        "magic_number": journal.magic_number,
        "account": journal.account,
        "order": journal.order_id,
        "deal": journal.deal_id,
        "matched_position": result_to_dict(matched_position),
        "matched_order": result_to_dict(matched_order),
        "matched_deal": result_to_dict(matched_deal),
    }


def first_matching_position(journal: SentJournal, positions: Sequence[Any]) -> Any | None:
    for position in positions:
        if position_matches(position, symbol=journal.symbol, magic=journal.magic_number):
            return position
    return None


def first_matching_order(journal: SentJournal, history_orders: Sequence[Any]) -> Any | None:
    if journal.order_id is None:
        return None
    for order in history_orders:
        data = result_to_dict(order) or {}
        if not history_item_matches_scope(data, symbol=journal.symbol, magic=journal.magic_number):
            continue
        if id_matches(data, journal.order_id, ("ticket", "order")):
            return order
    return None


def first_matching_deal(journal: SentJournal, history_deals: Sequence[Any]) -> Any | None:
    for deal in history_deals:
        data = result_to_dict(deal) or {}
        if not history_item_matches_scope(data, symbol=journal.symbol, magic=journal.magic_number):
            continue
        if journal.deal_id is not None and id_matches(data, journal.deal_id, ("ticket", "deal")):
            return deal
        if journal.order_id is not None and id_matches(data, journal.order_id, ("order",)):
            return deal
    return None


def history_item_matches_scope(data: Mapping[str, Any], *, symbol: str, magic: int) -> bool:
    item_symbol = data.get("symbol")
    if item_symbol and str(item_symbol) != symbol:
        return False
    item_magic = _int_or_none(data.get("magic"))
    if item_magic is not None and item_magic != magic:
        return False
    return True


def id_matches(data: Mapping[str, Any], target: int, fields: Sequence[str]) -> bool:
    return any(_int_or_none(data.get(field)) == target for field in fields)


def block_history_query_failed(event: dict[str, Any], sent_journals: Sequence[SentJournal], message: str) -> dict[str, Any]:
    event["history_matches"].extend(
        {
            "journal_path": str(journal.path),
            "classification": CLASS_HISTORY_QUERY_FAILED,
            "symbol": journal.symbol,
            "magic_number": journal.magic_number,
            "account": journal.account,
            "order": journal.order_id,
            "deal": journal.deal_id,
            "matched_position": None,
            "matched_order": None,
            "matched_deal": None,
            "error": message,
        }
        for journal in sent_journals
    )
    update_counts_and_decision(event)
    return event


def update_counts_and_decision(event: dict[str, Any]) -> None:
    classifications = [str(match.get("classification")) for match in event["history_matches"]]
    event["open_positions_matched"] = classifications.count(CLASS_OPEN_POSITION_MATCHED)
    event["closed_in_history"] = classifications.count(CLASS_CLOSED_IN_HISTORY)
    event["missing_in_history"] = classifications.count(CLASS_SENT_BUT_NOT_FOUND)
    event["history_query_failed"] = classifications.count(CLASS_HISTORY_QUERY_FAILED)
    event["invalid_sent_journals"] = classifications.count(CLASS_INVALID_SENT_JOURNAL)

    reason_codes: list[str] = []
    if event["invalid_sent_journals"]:
        reason_codes.append(REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING)
    if event["missing_in_history"]:
        reason_codes.append(REASON_SENT_BUT_NOT_FOUND)
    if event["history_query_failed"]:
        reason_codes.append(REASON_HISTORY_QUERY_FAILED)
    if reason_codes:
        event["final_decision"] = "BLOCK"
        event["reason_codes"] = reason_codes
        event["reasons"] = [history_reason_text(code) for code in reason_codes]


def history_reason_text(code: str) -> str:
    if code == REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING:
        return f"{code}: one or more candidate sent journals are missing required reconciliation fields"
    if code == REASON_SENT_BUT_NOT_FOUND:
        return f"{code}: one or more accepted sent journals were not found in positions or MT5 history"
    if code == REASON_HISTORY_QUERY_FAILED:
        return f"{code}: MT5 history or position query failed"
    return code


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def first_text(*values: Any) -> str:
    for value in values:
        if value:
            return str(value)
    return ""


def first_int(*values: Any) -> int | None:
    for value in values:
        parsed = _int_or_none(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _nested(source: Mapping[str, Any], *path: str) -> Any:
    value: Any = source
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile accepted demo order journals against MT5 positions/history.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--config", default="config/xm_gold_ai_trader.demo_order_once.yaml")
    parser.add_argument("--lookback-days", type=int, default=90)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
