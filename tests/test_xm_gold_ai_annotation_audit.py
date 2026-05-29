from __future__ import annotations

import inspect
import json

import scripts.audit_ai_annotations as audit_module
from scripts.audit_ai_annotations import (
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    REASON_DUPLICATE_ANNOTATION_FOR_SOURCE_HASH,
    REASON_SOURCE_JOURNAL_HASH_MISMATCH,
    REASON_SOURCE_JOURNAL_MISSING,
    audit_ai_annotations,
    sha256_file,
)
from scripts.annotate_dry_run_signals import REASON_ANNOTATION_FORBIDDEN_FIELD


def test_valid_annotation_passes(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path)

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "PASS"
    assert report["annotation_count"] == 1
    assert report["valid_annotations"] == 1
    assert report["rejected_annotations"] == 0
    assert report["reason_codes"] == []
    assert report["orders_sent"] == 0
    assert report["order_check_called"] is False
    assert report["order_send_called"] is False


def test_modified_source_hash_warns_or_blocks(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path)
    write_source_journal(source_path, final_decision="BLOCK", extra={"changed": True})

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] in {"WARN", "BLOCK"}
    assert REASON_SOURCE_JOURNAL_HASH_MISMATCH in report["reason_codes"]
    assert report["drift_warnings"] > 0


def test_forbidden_field_blocks(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    annotation = valid_annotation() | {"lot": "0.01"}
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, annotation=annotation)

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "BLOCK"
    assert REASON_ANNOTATION_FORBIDDEN_FIELD in report["reason_codes"]
    assert report["forbidden_violations"] > 0


def test_forbidden_free_text_trading_instruction_blocks(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    annotation = valid_annotation() | {"risk_notes": "Use BUY now."}
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, annotation=annotation)

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "BLOCK"
    assert REASON_ANNOTATION_FORBIDDEN_FIELD in report["reason_codes"]
    assert report["forbidden_violations"] == 1


def test_duplicate_annotation_warns(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation_a.json", source_path=source_path)
    write_annotation(tmp_path / "annotations" / "annotation_b.json", source_path=source_path)

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "WARN"
    assert REASON_DUPLICATE_ANNOTATION_FOR_SOURCE_HASH in report["reason_codes"]
    assert report["drift_warnings"] == 1


def test_missing_source_blocks(tmp_path):
    source_path = tmp_path / "dry_run" / "missing.json"
    write_annotation(
        tmp_path / "annotations" / "annotation.json",
        source_path=source_path,
        source_hash="missing-source-hash",
    )

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "BLOCK"
    assert REASON_SOURCE_JOURNAL_MISSING in report["reason_codes"]


def test_orders_sent_nonzero_blocks(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, orders_sent=1)

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "BLOCK"
    assert REASON_ANNOTATION_ORDERS_SENT_NONZERO in report["reason_codes"]
    assert report["orders_sent"] == 0


def test_source_final_decision_drift_blocks(tmp_path):
    source_path = write_source_journal(tmp_path / "dry_run" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, final_decision="SIGNAL")

    report = audit_ai_annotations(tmp_path / "annotations")

    assert report["final_decision"] == "BLOCK"
    assert "SOURCE_FINAL_DECISION_DRIFT" in report["reason_codes"]


def test_audit_script_does_not_call_order_check_or_order_send():
    source = inspect.getsource(audit_module)

    assert "order_check(" not in source
    assert "order_send(" not in source


def write_source_journal(path, *, final_decision: str, extra: dict | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "timestamp_utc": "2026-05-28T00:00:00+00:00",
        "final_decision": final_decision,
        "reason_codes": [] if final_decision == "SIGNAL" else ["NO_ACTIONABLE_SIGNAL"],
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def write_annotation(
    path,
    *,
    source_path,
    source_hash: str | None = None,
    annotation: dict | None = None,
    final_decision: str = "BLOCK",
    orders_sent: int = 0,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "ai_signal_annotation",
        "annotation_schema_version": 1,
        "timestamp_utc": "2026-05-28T00:01:00+00:00",
        "source_journal_path": str(source_path),
        "source_journal_hash": source_hash or sha256_file(source_path),
        "source_final_decision": "BLOCK",
        "final_decision": final_decision,
        "annotation_status": "ACCEPTED",
        "annotation": annotation or valid_annotation(),
        "orders_sent": orders_sent,
        "order_check_called": False,
        "order_send_called": False,
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def valid_annotation() -> dict[str, str]:
    return {
        "market_regime": "neutral_or_unclear",
        "trend_context": "No actionable crossover condition was present on the latest closed bar.",
        "volatility_context": "ATR-derived context is treated as descriptive observation only.",
        "spread_context": "Observed spread was 55.0 points in the source journal.",
        "signal_quality_comment": "Read-only comment; source final decision remains BLOCK.",
        "risk_notes": "Risk preview was reviewed for guardrail context only.",
        "do_not_trade_reason": "This annotation never authorizes execution or changes the source decision.",
        "confidence_text": "Descriptive confidence only; not an execution confidence score.",
    }
