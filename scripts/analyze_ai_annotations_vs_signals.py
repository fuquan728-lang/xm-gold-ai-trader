from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_annotation_report import (
    REASON_ANNOTATION_ORDER_CHECK_CALLED,
    REASON_ANNOTATION_ORDER_SEND_CALLED,
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    load_annotation_journals,
)
from scripts.annotate_dry_run_signals import (
    DEFAULT_ANNOTATION_DIR,
    PROJECT,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
    sha256_file,
    validate_annotation,
)
from scripts.dry_run_signal_report import load_dry_run_journals
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR


MODE = "analyze_ai_annotations_vs_signals"

REASON_MISSING_AI_ANNOTATION = "MISSING_AI_ANNOTATION"
REASON_DUPLICATE_AI_ANNOTATION = "DUPLICATE_AI_ANNOTATION"
REASON_SOURCE_ORDERS_SENT_NONZERO = "SOURCE_ORDERS_SENT_NONZERO"
REASON_SOURCE_ORDER_CHECK_CALLED = "SOURCE_ORDER_CHECK_CALLED"
REASON_SOURCE_ORDER_SEND_CALLED = "SOURCE_ORDER_SEND_CALLED"
REASON_SOURCE_JOURNAL_MALFORMED = "SOURCE_JOURNAL_MALFORMED"
REASON_ANNOTATION_JOURNAL_MALFORMED = "ANNOTATION_JOURNAL_MALFORMED"

BLOCK_REASON_CODES = {
    REASON_SOURCE_ORDERS_SENT_NONZERO,
    REASON_SOURCE_ORDER_CHECK_CALLED,
    REASON_SOURCE_ORDER_SEND_CALLED,
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    REASON_ANNOTATION_ORDER_CHECK_CALLED,
    REASON_ANNOTATION_ORDER_SEND_CALLED,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
}
WARN_REASON_CODES = {
    REASON_MISSING_AI_ANNOTATION,
    REASON_DUPLICATE_AI_ANNOTATION,
    REASON_SOURCE_JOURNAL_MALFORMED,
    REASON_ANNOTATION_JOURNAL_MALFORMED,
}


def main() -> int:
    args = parse_args()
    report = analyze_ai_annotations_vs_signals(
        source_dir=Path(args.source_dir),
        annotation_dir=Path(args.annotation_dir),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def analyze_ai_annotations_vs_signals(*, source_dir: Path, annotation_dir: Path) -> dict[str, Any]:
    source_entries = load_dry_run_journals(source_dir)
    annotation_entries = load_annotation_journals(annotation_dir)
    source_records = build_source_records(source_entries)
    annotation_records = build_annotation_records(annotation_entries)
    annotation_by_hash: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in annotation_records:
        source_hash = record.get("source_journal_hash")
        if source_hash:
            annotation_by_hash[str(source_hash)].append(record)

    reason_counter: Counter[str] = Counter()
    reasons: list[str] = []
    source_safety = scan_source_safety(source_records)
    annotation_safety = scan_annotation_safety(annotation_records)
    reason_counter.update(source_safety["reason_code_counts"])
    reason_counter.update(annotation_safety["reason_code_counts"])
    reasons.extend(source_safety["reasons"])
    reasons.extend(annotation_safety["reasons"])

    total_joined = 0
    missing_annotations = 0
    duplicate_annotations = 0
    source_final_decision_counter: Counter[str] = Counter()
    market_regime_counter: Counter[str] = Counter()
    do_not_trade_counter: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    signal_vs_regime: defaultdict[str, Counter[str]] = defaultdict(Counter)
    block_reason_vs_ai_reason: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for record in source_records:
        if record["payload"] is None:
            reason_counter.update([REASON_SOURCE_JOURNAL_MALFORMED])
            continue
        source_payload = record["payload"]
        source_hash = record["source_journal_hash"]
        source_decision = str(source_payload.get("final_decision") or "UNKNOWN")
        source_final_decision_counter.update([source_decision])
        matches = annotation_by_hash.get(source_hash, [])
        accepted_matches = [match for match in matches if match.get("annotation_status") != "REJECTED"]
        if not matches:
            missing_annotations += 1
            reason_counter.update([REASON_MISSING_AI_ANNOTATION])
            reasons.append(f"{REASON_MISSING_AI_ANNOTATION}: no annotation found for source hash {source_hash}")
            continue
        total_joined += 1
        if len(matches) > 1:
            extra = len(matches) - 1
            duplicate_annotations += extra
            reason_counter.update({REASON_DUPLICATE_AI_ANNOTATION: extra})
            reasons.append(f"{REASON_DUPLICATE_AI_ANNOTATION}: {len(matches)} annotations for source hash {source_hash}")

        for annotation_record in accepted_matches:
            annotation = annotation_record.get("annotation") or {}
            market_regime = str(annotation.get("market_regime") or "UNKNOWN")
            do_not_trade_reason = str(annotation.get("do_not_trade_reason") or "UNKNOWN")
            confidence_text = str(annotation.get("confidence_text") or "UNKNOWN")
            market_regime_counter.update([market_regime])
            do_not_trade_counter.update([do_not_trade_reason])
            confidence_counter.update([confidence_text])
            signal_vs_regime[source_decision].update([market_regime])
            for code in source_payload.get("reason_codes") or []:
                block_reason_vs_ai_reason[str(code)].update([do_not_trade_reason])

    malformed_annotations = sum(1 for record in annotation_records if record["payload"] is None)
    if malformed_annotations:
        reason_counter.update({REASON_ANNOTATION_JOURNAL_MALFORMED: malformed_annotations})
        reasons.append(f"{REASON_ANNOTATION_JOURNAL_MALFORMED}: {malformed_annotations} malformed annotation journals")

    has_block = any(code in BLOCK_REASON_CODES for code in reason_counter)
    has_warn = any(code in WARN_REASON_CODES for code in reason_counter)
    final_decision = "BLOCK" if has_block else "WARN" if has_warn else "PASS"

    return {
        "project": PROJECT,
        "mode": MODE,
        "source_dir": str(source_dir),
        "annotation_dir": str(annotation_dir),
        "total_sources": len([record for record in source_records if record["payload"] is not None]),
        "total_annotations": len([record for record in annotation_records if record["payload"] is not None]),
        "total_joined": total_joined,
        "missing_annotations": missing_annotations,
        "duplicate_annotations": duplicate_annotations,
        "source_final_decision_counts": dict(sorted(source_final_decision_counter.items())),
        "annotation_market_regime_counts": dict(sorted(market_regime_counter.items())),
        "annotation_do_not_trade_reason_counts": dict(sorted(do_not_trade_counter.items())),
        "annotation_confidence_text_counts": dict(sorted(confidence_counter.items())),
        "signal_vs_regime_matrix": matrix_to_dict(signal_vs_regime),
        "block_reason_vs_ai_reason_matrix": matrix_to_dict(block_reason_vs_ai_reason),
        "source_safety": source_safety,
        "annotation_safety": annotation_safety,
        "forbidden_violations": annotation_safety["forbidden_violations"],
        "reason_codes": sorted(reason_counter),
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "reasons": reasons,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
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


def build_source_records(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in entries:
        path = Path(entry["path"])
        records.append(
            {
                "path": str(path),
                "payload": entry["payload"],
                "source_journal_hash": sha256_file(path),
                "parse_reason_codes": list(entry.get("reason_codes") or []),
            }
        )
    return records


def build_annotation_records(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in entries:
        payload = entry["payload"]
        record: dict[str, Any] = {
            "path": entry["path"],
            "payload": payload,
            "parse_reason_codes": list(entry.get("reason_codes") or []),
        }
        if payload is not None:
            record.update(
                {
                    "source_journal_hash": payload.get("source_journal_hash"),
                    "annotation_status": payload.get("annotation_status"),
                    "annotation": payload.get("annotation"),
                }
            )
        records.append(record)
    return records


def scan_source_safety(records: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    reasons: list[str] = []
    observed_orders_sent_sum = 0
    order_check_called_count = 0
    order_send_called_count = 0
    for record in records:
        payload = record["payload"]
        if payload is None:
            reason_counter.update([REASON_SOURCE_JOURNAL_MALFORMED])
            reasons.append(f"{REASON_SOURCE_JOURNAL_MALFORMED}: {record['path']}")
            continue
        orders_sent = int(payload.get("orders_sent") or 0)
        observed_orders_sent_sum += orders_sent
        if orders_sent != 0:
            reason_counter.update([REASON_SOURCE_ORDERS_SENT_NONZERO])
            reasons.append(f"{REASON_SOURCE_ORDERS_SENT_NONZERO}: {record['path']} has orders_sent {orders_sent}")
        if bool(payload.get("order_check_called")):
            order_check_called_count += 1
            reason_counter.update([REASON_SOURCE_ORDER_CHECK_CALLED])
            reasons.append(f"{REASON_SOURCE_ORDER_CHECK_CALLED}: {record['path']}")
        if bool(payload.get("order_send_called")):
            order_send_called_count += 1
            reason_counter.update([REASON_SOURCE_ORDER_SEND_CALLED])
            reasons.append(f"{REASON_SOURCE_ORDER_SEND_CALLED}: {record['path']}")
    return {
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "order_check_called_count": order_check_called_count,
        "order_send_called_count": order_send_called_count,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "reasons": reasons,
    }


def scan_annotation_safety(records: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    reasons: list[str] = []
    observed_orders_sent_sum = 0
    order_check_called_count = 0
    order_send_called_count = 0
    forbidden_violations = 0
    for record in records:
        payload = record["payload"]
        if payload is None:
            reason_counter.update([REASON_ANNOTATION_JOURNAL_MALFORMED])
            reasons.append(f"{REASON_ANNOTATION_JOURNAL_MALFORMED}: {record['path']}")
            continue
        orders_sent = int(payload.get("orders_sent") or 0)
        observed_orders_sent_sum += orders_sent
        if orders_sent != 0:
            reason_counter.update([REASON_ANNOTATION_ORDERS_SENT_NONZERO])
            reasons.append(f"{REASON_ANNOTATION_ORDERS_SENT_NONZERO}: {record['path']} has orders_sent {orders_sent}")
        if bool(payload.get("order_check_called")):
            order_check_called_count += 1
            reason_counter.update([REASON_ANNOTATION_ORDER_CHECK_CALLED])
            reasons.append(f"{REASON_ANNOTATION_ORDER_CHECK_CALLED}: {record['path']}")
        if bool(payload.get("order_send_called")):
            order_send_called_count += 1
            reason_counter.update([REASON_ANNOTATION_ORDER_SEND_CALLED])
            reasons.append(f"{REASON_ANNOTATION_ORDER_SEND_CALLED}: {record['path']}")

        if payload.get("annotation_status") != "REJECTED":
            for violation in validate_annotation(payload.get("annotation")):
                reason_counter.update([violation["reason_code"]])
                reasons.append(violation["reason"])
                if violation["reason_code"] == REASON_ANNOTATION_FORBIDDEN_FIELD:
                    forbidden_violations += 1
    return {
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "order_check_called_count": order_check_called_count,
        "order_send_called_count": order_send_called_count,
        "forbidden_violations": forbidden_violations,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "reasons": reasons,
    }


def matrix_to_dict(matrix: Mapping[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {
        row: dict(sorted(counter.items()))
        for row, counter in sorted(matrix.items())
    }


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader AI annotations vs dry-run signals")
    print(f"final_decision: {report['final_decision']}")
    print(f"total_joined: {report['total_joined']}")
    print(f"missing_annotations: {report['missing_annotations']}")
    print(f"duplicate_annotations: {report['duplicate_annotations']}")
    print(f"forbidden_violations: {report['forbidden_violations']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze read-only AI annotations against baseline dry-run signals.")
    parser.add_argument("--source-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--annotation-dir", default=str(DEFAULT_ANNOTATION_DIR))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
