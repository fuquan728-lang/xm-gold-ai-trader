from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.annotate_dry_run_signals import (
    ANNOTATION_SCHEMA_VERSION,
    DEFAULT_ANNOTATION_DIR,
    PROJECT,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
    REASON_ANNOTATION_SCHEMA_FIELD_MISSING,
    validate_annotation,
)
from scripts.dry_run_signal_report import REASON_JOURNAL_JSON_INVALID, REASON_JOURNAL_NOT_OBJECT


MODE = "ai_annotation_report"
REASON_ANNOTATION_REQUIRED_FIELD_MISSING = "ANNOTATION_REQUIRED_FIELD_MISSING"
REASON_ANNOTATION_ORDERS_SENT_NONZERO = "ANNOTATION_ORDERS_SENT_NONZERO"
REASON_ANNOTATION_ORDER_CHECK_CALLED = "ANNOTATION_ORDER_CHECK_CALLED"
REASON_ANNOTATION_ORDER_SEND_CALLED = "ANNOTATION_ORDER_SEND_CALLED"


def main() -> int:
    args = parse_args()
    report = summarize_ai_annotations(Path(args.annotation_dir))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def summarize_ai_annotations(annotation_dir: Path) -> dict[str, Any]:
    entries = load_annotation_journals(annotation_dir)
    reason_counter: Counter[str] = Counter()
    market_regime_counter: Counter[str] = Counter()
    do_not_trade_counter: Counter[str] = Counter()
    valid_annotations = 0
    rejected_annotations = 0
    malformed_annotations = 0
    forbidden_field_violations = 0
    observed_orders_sent_sum = 0
    order_check_called_count = 0
    order_send_called_count = 0
    missing_required_count = 0

    for entry in entries:
        payload = entry["payload"]
        if payload is None:
            malformed_annotations += 1
            reason_counter.update(entry["reason_codes"])
            continue

        missing = missing_required_fields(payload)
        if missing:
            missing_required_count += 1
            reason_counter.update([REASON_ANNOTATION_REQUIRED_FIELD_MISSING])

        observed_orders_sent_sum += int(payload.get("orders_sent") or 0)
        if int(payload.get("orders_sent") or 0) != 0:
            reason_counter.update([REASON_ANNOTATION_ORDERS_SENT_NONZERO])
        if bool(payload.get("order_check_called")):
            order_check_called_count += 1
            reason_counter.update([REASON_ANNOTATION_ORDER_CHECK_CALLED])
        if bool(payload.get("order_send_called")):
            order_send_called_count += 1
            reason_counter.update([REASON_ANNOTATION_ORDER_SEND_CALLED])

        if payload.get("annotation_status") == "REJECTED":
            rejected_annotations += 1
            reason_counter.update(payload.get("reason_codes") or [])
            continue

        annotation = payload.get("annotation")
        violations = validate_annotation(annotation)
        if violations:
            reason_counter.update([item["reason_code"] for item in violations])
            forbidden_field_violations += sum(
                1 for item in violations if item["reason_code"] == REASON_ANNOTATION_FORBIDDEN_FIELD
            )
            continue

        valid_annotations += 1
        market_regime_counter.update([str(annotation.get("market_regime"))])
        do_not_trade_counter.update([str(annotation.get("do_not_trade_reason"))])

    block_codes = {
        REASON_ANNOTATION_FORBIDDEN_FIELD,
        REASON_ANNOTATION_ORDERS_SENT_NONZERO,
        REASON_ANNOTATION_ORDER_CHECK_CALLED,
        REASON_ANNOTATION_ORDER_SEND_CALLED,
    }
    final_decision = "PASS"
    if any(code in reason_counter for code in block_codes):
        final_decision = "BLOCK"
    elif rejected_annotations or malformed_annotations or missing_required_count:
        final_decision = "WARN"

    return {
        "project": PROJECT,
        "mode": MODE,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_dir": str(annotation_dir),
        "total_files": len(entries),
        "annotations": valid_annotations,
        "valid_annotations": valid_annotations,
        "rejected_annotations": rejected_annotations,
        "malformed_annotations": malformed_annotations,
        "missing_required_field_annotations": missing_required_count,
        "market_regime_counts": dict(sorted(market_regime_counter.items())),
        "do_not_trade_reason_counts": dict(sorted(do_not_trade_counter.items())),
        "forbidden_field_violations": forbidden_field_violations,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "reason_codes": sorted(reason_counter),
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "order_check_called_count": order_check_called_count,
        "order_send_called_count": order_send_called_count,
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
        "final_decision": final_decision,
    }


def load_annotation_journals(annotation_dir: Path) -> list[dict[str, Any]]:
    if not annotation_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(annotation_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_JOURNAL_JSON_INVALID],
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(payload, dict):
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_JOURNAL_NOT_OBJECT],
                    "error": "annotation JSON root is not an object",
                }
            )
            continue
        entries.append({"path": str(path), "payload": payload, "reason_codes": [], "error": None})
    return entries


def missing_required_fields(payload: Mapping[str, Any]) -> list[str]:
    required = (
        "project",
        "mode",
        "source_journal_path",
        "source_journal_hash",
        "annotation_schema_version",
        "orders_sent",
        "order_check_called",
        "order_send_called",
        "annotation_status",
        "final_decision",
    )
    missing = [field for field in required if field not in payload]
    if payload.get("annotation_status") == "ACCEPTED" and "annotation" not in payload:
        missing.append("annotation")
    if payload.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
        missing.append("annotation_schema_version")
    if payload.get("annotation_status") == "ACCEPTED" and payload.get("annotation") is None:
        missing.append("annotation")
    return missing


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader AI annotation report")
    print(f"final_decision: {report['final_decision']}")
    print(f"annotations: {report['annotations']}")
    print(f"rejected annotations: {report['rejected_annotations']}")
    print(f"malformed annotations: {report['malformed_annotations']}")
    print(f"forbidden field violations: {report['forbidden_field_violations']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize and validate read-only AI annotation journals.")
    parser.add_argument("--annotation-dir", default=str(DEFAULT_ANNOTATION_DIR))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
