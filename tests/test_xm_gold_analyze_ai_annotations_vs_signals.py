from __future__ import annotations

import inspect
import json

import scripts.analyze_ai_annotations_vs_signals as analysis_module
from scripts.analyze_ai_annotations_vs_signals import (
    REASON_ANNOTATION_ORDERS_SENT_NONZERO,
    REASON_DUPLICATE_AI_ANNOTATION,
    REASON_MISSING_AI_ANNOTATION,
    analyze_ai_annotations_vs_signals,
)
from scripts.annotate_dry_run_signals import REASON_ANNOTATION_FORBIDDEN_FIELD, sha256_file


def test_joins_annotation_to_source_by_hash(tmp_path):
    source_path = write_source(tmp_path / "signals" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path)

    report = analyze_ai_annotations_vs_signals(
        source_dir=tmp_path / "signals",
        annotation_dir=tmp_path / "annotations",
    )

    assert report["final_decision"] == "PASS"
    assert report["total_joined"] == 1
    assert report["missing_annotations"] == 0
    assert report["source_final_decision_counts"] == {"BLOCK": 1}
    assert report["annotation_market_regime_counts"] == {"neutral_or_unclear": 1}
    assert report["signal_vs_regime_matrix"] == {"BLOCK": {"neutral_or_unclear": 1}}
    assert report["block_reason_vs_ai_reason_matrix"] == {
        "NO_ACTIONABLE_SIGNAL": {"This annotation never authorizes execution or changes the source decision.": 1}
    }


def test_missing_annotation_warns(tmp_path):
    write_source(tmp_path / "signals" / "source.json", final_decision="BLOCK")

    report = analyze_ai_annotations_vs_signals(
        source_dir=tmp_path / "signals",
        annotation_dir=tmp_path / "annotations",
    )

    assert report["final_decision"] == "WARN"
    assert report["missing_annotations"] == 1
    assert REASON_MISSING_AI_ANNOTATION in report["reason_codes"]


def test_duplicate_annotation_warns(tmp_path):
    source_path = write_source(tmp_path / "signals" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation_a.json", source_path=source_path)
    write_annotation(tmp_path / "annotations" / "annotation_b.json", source_path=source_path)

    report = analyze_ai_annotations_vs_signals(
        source_dir=tmp_path / "signals",
        annotation_dir=tmp_path / "annotations",
    )

    assert report["final_decision"] == "WARN"
    assert report["duplicate_annotations"] == 1
    assert REASON_DUPLICATE_AI_ANNOTATION in report["reason_codes"]


def test_forbidden_field_blocks(tmp_path):
    source_path = write_source(tmp_path / "signals" / "source.json", final_decision="BLOCK")
    annotation = valid_annotation() | {"lot": "0.01"}
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, annotation=annotation)

    report = analyze_ai_annotations_vs_signals(
        source_dir=tmp_path / "signals",
        annotation_dir=tmp_path / "annotations",
    )

    assert report["final_decision"] == "BLOCK"
    assert REASON_ANNOTATION_FORBIDDEN_FIELD in report["reason_codes"]
    assert report["forbidden_violations"] > 0


def test_orders_sent_nonzero_blocks(tmp_path):
    source_path = write_source(tmp_path / "signals" / "source.json", final_decision="BLOCK")
    write_annotation(tmp_path / "annotations" / "annotation.json", source_path=source_path, orders_sent=1)

    report = analyze_ai_annotations_vs_signals(
        source_dir=tmp_path / "signals",
        annotation_dir=tmp_path / "annotations",
    )

    assert report["final_decision"] == "BLOCK"
    assert REASON_ANNOTATION_ORDERS_SENT_NONZERO in report["reason_codes"]
    assert report["orders_sent"] == 0


def test_no_order_check_or_order_send_calls():
    source = inspect.getsource(analysis_module)

    assert "order_check(" not in source
    assert "order_send(" not in source


def write_source(path, *, final_decision: str):
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
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def write_annotation(path, *, source_path, annotation: dict | None = None, orders_sent: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "ai_signal_annotation",
        "annotation_schema_version": 1,
        "timestamp_utc": "2026-05-28T00:01:00+00:00",
        "source_journal_path": str(source_path),
        "source_journal_hash": sha256_file(source_path),
        "source_final_decision": "BLOCK",
        "final_decision": "BLOCK",
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
