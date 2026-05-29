from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preflight_order_check import load_or_default_config
from src.cli_contract import event_exit_code


PROJECT = "xm-gold-ai-trader"
MODE = "reconcile_demo_journal"
DEFAULT_JOURNAL_DIR = Path("logs/demo_orders")
JOURNAL_SCHEMA_VERSION = 1
SEVERITY_FAIL = "FAIL"
SEVERITY_WARNING = "WARNING"

REASON_NO_DEMO_JOURNALS = "NO_DEMO_JOURNALS"
REASON_LEGACY_JOURNAL_SCHEMA = "LEGACY_JOURNAL_SCHEMA"
REASON_UNKNOWN_JOURNAL_SCHEMA = "UNKNOWN_JOURNAL_SCHEMA"
REASON_JOURNAL_JSON_INVALID = "JOURNAL_JSON_INVALID"
REASON_JOURNAL_NOT_OBJECT = "JOURNAL_NOT_OBJECT"
REASON_JOURNAL_REQUIRED_FIELD_MISSING = "JOURNAL_REQUIRED_FIELD_MISSING"
REASON_JOURNAL_SYMBOL_MISMATCH = "JOURNAL_SYMBOL_MISMATCH"
REASON_JOURNAL_MAGIC_MISMATCH = "JOURNAL_MAGIC_MISMATCH"
REASON_JOURNAL_ORDER_SEND_RESULT_MISSING = "JOURNAL_ORDER_SEND_RESULT_MISSING"
REASON_JOURNAL_POSITION_VERIFICATION_MISSING = "JOURNAL_POSITION_VERIFICATION_MISSING"
REASON_JOURNAL_ACCOUNT_SUMMARY_MISSING = "JOURNAL_ACCOUNT_SUMMARY_MISSING"
REASON_DEMO_ORDER_CONFIRMATION_MISSING = "DEMO_ORDER_CONFIRMATION_MISSING"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    path: Path
    payload: dict[str, Any] | None
    parse_error: str | None = None


def main() -> int:
    args = parse_args()
    config = load_or_default_config(args.config)
    event = reconcile_demo_journal(
        journal_dir=Path(args.journal_dir),
        expected_symbol=args.symbol or config.symbol,
        project_magic=config.magic_number,
    )
    print(json.dumps(event, indent=2, sort_keys=True, default=str))
    return event_exit_code(event)


def reconcile_demo_journal(*, journal_dir: Path, expected_symbol: str, project_magic: int) -> dict[str, Any]:
    entries = load_journal_entries(journal_dir)
    findings = reconcile_entries(entries=entries, expected_symbol=expected_symbol, project_magic=project_magic)
    fail_findings = [item for item in findings if item["severity"] == SEVERITY_FAIL]
    warning_findings = [item for item in findings if item["severity"] == SEVERITY_WARNING]
    event = {
        "project": PROJECT,
        "mode": MODE,
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "orders_sent": 0,
        "final_decision": "ALLOW",
        "reason_codes": [],
        "reasons": [],
        "warning_codes": unique_codes(warning_findings),
        "warnings": [finding["message"] for finding in warning_findings],
        "journal_dir": str(journal_dir),
        "entries_checked": len(entries),
        "project_magic": project_magic,
        "expected_symbol": expected_symbol,
        "findings": findings,
        "failed_audit_journals": count_paths(fail_findings),
        "warning_journals": count_paths(warning_findings),
    }
    if not entries:
        event["final_decision"] = "BLOCK"
        event["reason_codes"] = [REASON_NO_DEMO_JOURNALS]
        event["reasons"] = [f"{REASON_NO_DEMO_JOURNALS}: no demo order journals found"]
    elif fail_findings:
        event["final_decision"] = "BLOCK"
        event["reason_codes"] = unique_codes(fail_findings)
        event["reasons"] = [finding["message"] for finding in fail_findings]
    return event


def load_journal_entries(journal_dir: Path) -> list[JournalEntry]:
    entries: list[JournalEntry] = []
    for path in sorted(journal_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            entries.append(JournalEntry(path=path, payload=None, parse_error=str(exc)))
            continue
        if not isinstance(payload, dict):
            entries.append(JournalEntry(path=path, payload=None, parse_error="journal root is not a JSON object"))
            continue
        entries.append(JournalEntry(path=path, payload=payload))
    return entries


def reconcile_entries(*, entries: list[JournalEntry], expected_symbol: str, project_magic: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in entries:
        if entry.payload is None:
            code = REASON_JOURNAL_JSON_INVALID
            if entry.parse_error == "journal root is not a JSON object":
                code = REASON_JOURNAL_NOT_OBJECT
            findings.append(finding(entry.path, code, entry.parse_error or "journal could not be parsed"))
            continue

        payload = entry.payload
        schema_version = payload.get("journal_schema_version")
        if schema_version is None:
            findings.append(
                finding(
                    entry.path,
                    REASON_LEGACY_JOURNAL_SCHEMA,
                    "journal_schema_version is missing",
                    severity=SEVERITY_WARNING,
                )
            )
            if is_sent_journal(payload):
                findings.extend(
                    reconcile_required_fields(
                        entry=entry,
                        payload=payload,
                        expected_symbol=expected_symbol,
                        project_magic=project_magic,
                    )
                )
            continue
        if _int_or_none(schema_version) != JOURNAL_SCHEMA_VERSION:
            findings.append(
                finding(
                    entry.path,
                    REASON_UNKNOWN_JOURNAL_SCHEMA,
                    f"journal_schema_version {schema_version!r} is not supported",
                )
            )
            continue

        findings.extend(
            reconcile_required_fields(
                entry=entry,
                payload=payload,
                expected_symbol=expected_symbol,
                project_magic=project_magic,
            )
        )
    return findings


def reconcile_required_fields(
    *,
    entry: JournalEntry,
    payload: Mapping[str, Any],
    expected_symbol: str,
    project_magic: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pre_confirmation_block = is_pre_confirmation_block(payload)
    for field_path in (
        ("project",),
        ("mode",),
        ("timestamp_utc",),
        ("final_decision",),
        ("reason_codes",),
        ("orders_sent",),
        ("block_stage",),
        ("side",),
        ("config", "magic_number"),
    ):
        if not has_path(payload, *field_path):
            findings.append(
                finding(
                    entry.path,
                    REASON_JOURNAL_REQUIRED_FIELD_MISSING,
                    f"required field {'.'.join(field_path)} is missing",
                )
            )

    if not pre_confirmation_block:
        for field_path in (
            ("account", "login"),
            ("account", "server"),
            ("symbol", "name"),
            ("candidate_order",),
            ("local_risk_decision",),
            ("order_check_result",),
        ):
            if not has_path(payload, *field_path):
                findings.append(
                    finding(
                        entry.path,
                        REASON_JOURNAL_REQUIRED_FIELD_MISSING,
                        f"required field {'.'.join(field_path)} is missing",
                    )
                )

    if payload.get("project") not in (None, "xm-gold-ai-trader"):
        findings.append(finding(entry.path, REASON_JOURNAL_REQUIRED_FIELD_MISSING, "project must be xm-gold-ai-trader"))

    symbols = symbol_values(payload)
    if not symbols or any(symbol != expected_symbol for symbol in symbols):
        findings.append(
            finding(
                entry.path,
                REASON_JOURNAL_SYMBOL_MISMATCH,
                f"symbol values {symbols!r} do not all match {expected_symbol!r}",
            )
        )

    magic_values = magic_number_values(payload)
    if not magic_values or any(magic != project_magic for magic in magic_values):
        findings.append(
            finding(
                entry.path,
                REASON_JOURNAL_MAGIC_MISMATCH,
                f"magic values {magic_values!r} do not all match {project_magic}",
            )
        )

    account = payload.get("account")
    if not pre_confirmation_block and (
        not isinstance(account, Mapping) or account.get("login") is None or not account.get("server")
    ):
        findings.append(
            finding(
                entry.path,
                REASON_JOURNAL_ACCOUNT_SUMMARY_MISSING,
                "account login and server must be recorded",
            )
        )

    if is_sent_journal(payload):
        for field_path in (("order_send_result",), ("position_verification",)):
            if not has_path(payload, *field_path):
                findings.append(
                    finding(
                        entry.path,
                        REASON_JOURNAL_REQUIRED_FIELD_MISSING,
                        f"required sent-order field {'.'.join(field_path)} is missing",
                    )
                )

        if not payload.get("order_send_result"):
            findings.append(
                finding(
                    entry.path,
                    REASON_JOURNAL_ORDER_SEND_RESULT_MISSING,
                    "order_send_result is required when orders_sent == 1",
                )
            )

        if not isinstance(payload.get("position_verification"), Mapping):
            findings.append(
                finding(
                    entry.path,
                    REASON_JOURNAL_POSITION_VERIFICATION_MISSING,
                    "position_verification object is required when orders_sent == 1",
                )
            )
    return findings


def is_sent_journal(payload: Mapping[str, Any]) -> bool:
    return _int_or_none(payload.get("orders_sent")) == 1 or payload.get("final_decision") == "SENT"


def is_pre_confirmation_block(payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("final_decision") == "BLOCK"
        and _int_or_none(payload.get("orders_sent")) == 0
        and REASON_DEMO_ORDER_CONFIRMATION_MISSING in (payload.get("reason_codes") or [])
        and payload.get("block_stage") == "pre_confirmation"
    )


def symbol_values(payload: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    config_symbol = _nested(payload, "config", "symbol")
    candidate_symbol = _nested(payload, "candidate_order", "symbol")
    symbol_name = _nested(payload, "symbol", "name")
    side_symbol = payload.get("symbol") if isinstance(payload.get("symbol"), str) else None
    for value in (config_symbol, candidate_symbol, symbol_name, side_symbol):
        if value:
            values.append(str(value))
    return values


def magic_number_values(payload: Mapping[str, Any]) -> list[int]:
    values: list[int] = []
    for value in (
        _nested(payload, "config", "magic_number"),
        _nested(payload, "candidate_order", "mt5_request", "magic"),
        _nested(payload, "order_send_result", "request", "magic"),
    ):
        if value is None:
            continue
        try:
            values.append(int(value))
        except (TypeError, ValueError):
            values.append(-1)
    return values


def finding(path: Path, code: str, message: str, severity: str = SEVERITY_FAIL) -> dict[str, Any]:
    return {"path": str(path), "severity": severity, "reason_code": code, "message": f"{code}: {message}"}


def unique_codes(findings: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for item in findings:
        code = str(item["reason_code"])
        if code not in codes:
            codes.append(code)
    return codes


def count_paths(findings: list[dict[str, Any]]) -> int:
    return len({str(item["path"]) for item in findings})


def has_path(source: Mapping[str, Any], *path: str) -> bool:
    value: Any = source
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return False
        value = value[key]
    return True


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit demo order JSON journals without sending orders.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--config", default="config/xm_gold_ai_trader.demo_order_once.yaml")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
