from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ai_annotation_report import (
    REASON_ANNOTATION_ORDER_CHECK_CALLED,
    REASON_ANNOTATION_ORDER_SEND_CALLED,
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    REASON_ANNOTATION_REQUIRED_FIELD_MISSING,
    load_annotation_journals,
)
from scripts.annotate_dry_run_signals import (
    ANNOTATION_SCHEMA_VERSION,
    DEFAULT_ANNOTATION_DIR,
    PROJECT,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
    validate_annotation,
)
from scripts.dry_run_signal_report import REASON_JOURNAL_JSON_INVALID, REASON_JOURNAL_NOT_OBJECT


MODE = "audit_ai_annotations"

REASON_ANNOTATION_SCHEMA_VERSION_MISMATCH = "ANNOTATION_SCHEMA_VERSION_MISMATCH"
REASON_ANNOTATION_WITHOUT_SOURCE = "ANNOTATION_WITHOUT_SOURCE"
REASON_SOURCE_JOURNAL_MISSING = "SOURCE_JOURNAL_MISSING"
REASON_SOURCE_JOURNAL_HASH_MISMATCH = "SOURCE_JOURNAL_HASH_MISMATCH"
REASON_SOURCE_JOURNAL_MODIFIED_AFTER_ANNOTATION = "SOURCE_JOURNAL_MODIFIED_AFTER_ANNOTATION"
REASON_SOURCE_FINAL_DECISION_DRIFT = "SOURCE_FINAL_DECISION_DRIFT"
REASON_DUPLICATE_ANNOTATION_FOR_SOURCE_HASH = "DUPLICATE_ANNOTATION_FOR_SOURCE_HASH"
REASON_SOURCE_JOURNAL_READ_FAILED = "SOURCE_JOURNAL_READ_FAILED"
REASON_SOURCE_JOURNAL_NOT_OBJECT = "SOURCE_JOURNAL_NOT_OBJECT"

BLOCK_REASON_CODES = {
    REASON_JOURNAL_JSON_INVALID,
    REASON_JOURNAL_NOT_OBJECT,
    REASON_ANNOTATION_REQUIRED_FIELD_MISSING,
    REASON_ANNOTATION_WITHOUT_SOURCE,
    REASON_SOURCE_JOURNAL_MISSING,
    REASON_SOURCE_JOURNAL_READ_FAILED,
    REASON_SOURCE_JOURNAL_NOT_OBJECT,
    REASON_SOURCE_FINAL_DECISION_DRIFT,
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    REASON_ANNOTATION_ORDER_CHECK_CALLED,
    REASON_ANNOTATION_ORDER_SEND_CALLED,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
}
WARN_REASON_CODES = {
    REASON_ANNOTATION_SCHEMA_VERSION_MISMATCH,
    REASON_SOURCE_JOURNAL_HASH_MISMATCH,
    REASON_SOURCE_JOURNAL_MODIFIED_AFTER_ANNOTATION,
    REASON_DUPLICATE_ANNOTATION_FOR_SOURCE_HASH,
}


def main() -> int:
    args = parse_args()
    report = audit_ai_annotations(Path(args.annotation_dir))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def audit_ai_annotations(annotation_dir: Path) -> dict[str, Any]:
    entries = load_annotation_journals(annotation_dir)
    reason_counter: Counter[str] = Counter()
    audit_results: list[dict[str, Any]] = []
    source_hash_paths: defaultdict[str, list[str]] = defaultdict(list)
    valid_annotations = 0
    rejected_annotations = 0
    forbidden_violations = 0

    for entry in entries:
        path = Path(entry["path"])
        payload = entry["payload"]
        result = audit_entry(path=path, payload=payload, parse_reason_codes=entry.get("reason_codes") or [])
        audit_results.append(result)
        reason_counter.update(result["reason_codes"])
        forbidden_violations += result["forbidden_violations"]
        if payload is not None and payload.get("annotation_status") == "REJECTED":
            rejected_annotations += 1
        if result["status"] == "VALID":
            valid_annotations += 1
        source_hash = result.get("source_journal_hash")
        if source_hash:
            source_hash_paths[str(source_hash)].append(str(path))

    duplicate_results = duplicate_source_hash_results(source_hash_paths)
    audit_results.extend(duplicate_results)
    for result in duplicate_results:
        reason_counter.update(result["reason_codes"])

    drift_warnings = sum(
        count for code, count in reason_counter.items() if code in WARN_REASON_CODES
    )
    has_block = any(code in BLOCK_REASON_CODES for code in reason_counter)
    has_warn = any(code in WARN_REASON_CODES for code in reason_counter)
    final_decision = "BLOCK" if has_block else "WARN" if has_warn else "PASS"

    return {
        "project": PROJECT,
        "mode": MODE,
        "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
        "annotation_dir": str(annotation_dir),
        "annotation_count": len(entries),
        "valid_annotations": valid_annotations,
        "rejected_annotations": rejected_annotations,
        "drift_warnings": drift_warnings,
        "forbidden_violations": forbidden_violations,
        "reason_codes": sorted(reason_counter),
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "audit_results": audit_results,
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


def audit_entry(
    *,
    path: Path,
    payload: Mapping[str, Any] | None,
    parse_reason_codes: list[str],
) -> dict[str, Any]:
    codes: list[str] = []
    reasons: list[str] = []
    forbidden_violations = 0
    if payload is None:
        for code in parse_reason_codes:
            add_reason(codes, reasons, code, "annotation journal could not be parsed")
        return entry_result(path, "BLOCK", codes, reasons, forbidden_violations)

    required_missing = required_missing_fields(payload)
    if required_missing:
        add_reason(
            codes,
            reasons,
            REASON_ANNOTATION_REQUIRED_FIELD_MISSING,
            f"missing {', '.join(required_missing)}",
        )
    if payload.get("annotation_schema_version") != ANNOTATION_SCHEMA_VERSION:
        add_reason(
            codes,
            reasons,
            REASON_ANNOTATION_SCHEMA_VERSION_MISMATCH,
            f"expected {ANNOTATION_SCHEMA_VERSION}, got {payload.get('annotation_schema_version')!r}",
        )
    orders_sent = int_or_none(payload.get("orders_sent"))
    if orders_sent != 0:
        add_reason(codes, reasons, REASON_ANNOTATION_ORDERS_SENT_NONZERO, f"orders_sent is {orders_sent!r}")
    if bool(payload.get("order_check_called")):
        add_reason(codes, reasons, REASON_ANNOTATION_ORDER_CHECK_CALLED, "annotation recorded order_check_called true")
    if bool(payload.get("order_send_called")):
        add_reason(codes, reasons, REASON_ANNOTATION_ORDER_SEND_CALLED, "annotation recorded order_send_called true")

    if payload.get("annotation_status") == "ACCEPTED":
        violations = validate_annotation(payload.get("annotation"))
        for violation in violations:
            add_reason(codes, reasons, violation["reason_code"], violation["reason"])
            if violation["reason_code"] == REASON_ANNOTATION_FORBIDDEN_FIELD:
                forbidden_violations += 1

    source_path_value = payload.get("source_journal_path")
    source_hash = payload.get("source_journal_hash")
    if not source_path_value or not source_hash:
        add_reason(codes, reasons, REASON_ANNOTATION_WITHOUT_SOURCE, "source_journal_path/source_journal_hash is missing")
        return entry_result(path, "BLOCK", codes, reasons, forbidden_violations, source_hash=source_hash)

    source_path = resolve_source_path(source_path_value, annotation_path=path)
    if not source_path.exists():
        add_reason(codes, reasons, REASON_SOURCE_JOURNAL_MISSING, f"source journal does not exist: {source_path}")
        return entry_result(path, "BLOCK", codes, reasons, forbidden_violations, source_hash=source_hash)

    source_payload, source_error = load_source_payload(source_path)
    actual_hash = sha256_file(source_path)
    if actual_hash != source_hash:
        add_reason(
            codes,
            reasons,
            REASON_SOURCE_JOURNAL_HASH_MISMATCH,
            "source journal hash differs from annotation source_journal_hash",
        )
        add_reason(
            codes,
            reasons,
            REASON_SOURCE_JOURNAL_MODIFIED_AFTER_ANNOTATION,
            "source journal content changed after annotation was recorded",
        )
    if source_error:
        add_reason(codes, reasons, source_error[0], source_error[1])
    elif source_payload is not None:
        expected_decision = source_payload.get("final_decision")
        if payload.get("source_final_decision") != expected_decision or payload.get("final_decision") != expected_decision:
            add_reason(
                codes,
                reasons,
                REASON_SOURCE_FINAL_DECISION_DRIFT,
                (
                    f"annotation final decision/source_final_decision "
                    f"{payload.get('final_decision')!r}/{payload.get('source_final_decision')!r} "
                    f"does not match source {expected_decision!r}"
                ),
            )

    status = "BLOCK" if any(code in BLOCK_REASON_CODES for code in codes) else "WARN" if codes else "VALID"
    return entry_result(
        path,
        status,
        codes,
        reasons,
        forbidden_violations,
        source_path=str(source_path),
        source_hash=source_hash,
        actual_source_hash=actual_hash,
    )


def duplicate_source_hash_results(source_hash_paths: Mapping[str, list[str]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source_hash, paths in sorted(source_hash_paths.items()):
        if len(paths) <= 1:
            continue
        code = REASON_DUPLICATE_ANNOTATION_FOR_SOURCE_HASH
        results.append(
            {
                "path": None,
                "status": "WARN",
                "source_journal_hash": source_hash,
                "duplicate_paths": paths,
                "reason_codes": [code],
                "reasons": [f"{code}: {len(paths)} annotations reference source hash {source_hash}"],
                "forbidden_violations": 0,
            }
        )
    return results


def required_missing_fields(payload: Mapping[str, Any]) -> list[str]:
    required = (
        "source_journal_path",
        "source_journal_hash",
        "source_final_decision",
        "final_decision",
        "annotation_schema_version",
        "orders_sent",
        "order_check_called",
        "order_send_called",
        "annotation_status",
    )
    missing = [field for field in required if field not in payload]
    if payload.get("annotation_status") == "ACCEPTED" and "annotation" not in payload:
        missing.append("annotation")
    return missing


def resolve_source_path(source_path_value: Any, *, annotation_path: Path) -> Path:
    source_path = Path(str(source_path_value))
    if source_path.is_absolute():
        return source_path
    if source_path.exists():
        return source_path
    return annotation_path.parent / source_path


def load_source_payload(source_path: Path) -> tuple[Mapping[str, Any] | None, tuple[str, str] | None]:
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, (REASON_SOURCE_JOURNAL_READ_FAILED, f"source journal JSON is invalid: {exc}")
    if not isinstance(payload, Mapping):
        return None, (REASON_SOURCE_JOURNAL_NOT_OBJECT, "source journal root is not an object")
    return payload, None


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_reason(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    codes.append(code)
    reasons.append(f"{code}: {reason}")


def entry_result(
    path: Path,
    status: str,
    codes: list[str],
    reasons: list[str],
    forbidden_violations: int,
    *,
    source_path: str | None = None,
    source_hash: Any = None,
    actual_source_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "path": str(path),
        "status": status,
        "source_journal_path": source_path,
        "source_journal_hash": source_hash,
        "actual_source_hash": actual_source_hash,
        "reason_codes": codes,
        "reasons": reasons,
        "forbidden_violations": forbidden_violations,
    }


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader AI annotation audit")
    print(f"final_decision: {report['final_decision']}")
    print(f"annotation_count: {report['annotation_count']}")
    print(f"valid_annotations: {report['valid_annotations']}")
    print(f"rejected_annotations: {report['rejected_annotations']}")
    print(f"drift_warnings: {report['drift_warnings']}")
    print(f"forbidden_violations: {report['forbidden_violations']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit read-only AI annotation journals for drift and safety.")
    parser.add_argument("--annotation-dir", default=str(DEFAULT_ANNOTATION_DIR))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
