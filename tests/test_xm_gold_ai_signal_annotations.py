from __future__ import annotations

import inspect
import json

import scripts.ai_annotation_report as ai_annotation_report_module
import scripts.annotate_dry_run_signals as annotate_module
from scripts.ai_annotation_report import summarize_ai_annotations
from scripts.annotate_dry_run_signals import (
    ALLOWED_ANNOTATION_KEYS,
    REASON_ANNOTATION_FORBIDDEN_FIELD,
    REASON_SOURCE_JOURNAL_MALFORMED,
    annotate_dry_run_signals,
    validate_annotation,
)


def test_mock_annotation_writes_valid_schema(tmp_path):
    source_dir = tmp_path / "dry_run"
    output_dir = tmp_path / "annotations"
    write_source_journal(source_dir / "source.json")

    result = annotate_dry_run_signals(source_dir=source_dir, output_dir=output_dir)

    assert result["annotations_written"] == 1
    assert result["rejected_annotations"] == 0
    annotation_path = output_dir.glob("*.json").__next__()
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert payload["annotation_schema_version"] == 1
    assert payload["source_journal_hash"]
    assert payload["annotation_status"] == "ACCEPTED"
    assert set(payload["annotation"].keys()) == ALLOWED_ANNOTATION_KEYS
    assert validate_annotation(payload["annotation"]) == []
    assert payload["orders_sent"] == 0
    assert payload["order_check_called"] is False
    assert payload["order_send_called"] is False

    report = summarize_ai_annotations(output_dir)
    assert report["final_decision"] == "PASS"
    assert report["valid_annotations"] == 1
    assert report["forbidden_field_violations"] == 0


def test_forbidden_trading_field_is_rejected():
    annotation = valid_annotation()
    annotation["lot"] = "0.01"

    violations = validate_annotation(annotation)

    assert REASON_ANNOTATION_FORBIDDEN_FIELD in {item["reason_code"] for item in violations}


def test_annotation_cannot_alter_source_final_decision(tmp_path):
    source_dir = tmp_path / "dry_run"
    output_dir = tmp_path / "annotations"
    write_source_journal(source_dir / "source.json", final_decision="BLOCK")

    annotate_dry_run_signals(source_dir=source_dir, output_dir=output_dir)

    payload = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert payload["source_final_decision"] == "BLOCK"
    assert payload["final_decision"] == "BLOCK"
    assert "final_decision" not in payload["annotation"]


def test_annotation_report_detects_forbidden_trading_language(tmp_path):
    output_dir = tmp_path / "annotations"
    output_dir.mkdir()
    payload = accepted_annotation_journal(valid_annotation() | {"risk_notes": "Use BUY now."})
    (output_dir / "bad.json").write_text(json.dumps(payload), encoding="utf-8")

    report = summarize_ai_annotations(output_dir)

    assert report["final_decision"] == "BLOCK"
    assert report["forbidden_field_violations"] == 1
    assert REASON_ANNOTATION_FORBIDDEN_FIELD in report["reason_codes"]


def test_orders_sent_always_zero(tmp_path):
    source_dir = tmp_path / "dry_run"
    output_dir = tmp_path / "annotations"
    write_source_journal(source_dir / "source.json")

    result = annotate_dry_run_signals(source_dir=source_dir, output_dir=output_dir)
    report = summarize_ai_annotations(output_dir)
    payload = json.loads(next(output_dir.glob("*.json")).read_text(encoding="utf-8"))

    assert result["orders_sent"] == 0
    assert report["orders_sent"] == 0
    assert payload["orders_sent"] == 0


def test_annotation_scripts_do_not_call_order_check_or_order_send():
    annotate_source = inspect.getsource(annotate_module)
    report_source = inspect.getsource(ai_annotation_report_module)

    assert "order_check(" not in annotate_source
    assert "order_send(" not in annotate_source
    assert "order_check(" not in report_source
    assert "order_send(" not in report_source


def test_malformed_source_journal_is_handled_safely(tmp_path):
    source_dir = tmp_path / "dry_run"
    output_dir = tmp_path / "annotations"
    source_dir.mkdir()
    (source_dir / "bad.json").write_text("{bad", encoding="utf-8")

    result = annotate_dry_run_signals(source_dir=source_dir, output_dir=output_dir)
    report = summarize_ai_annotations(output_dir)

    assert result["malformed_source_journals"] == 1
    assert result["rejected_annotations"] == 1
    assert REASON_SOURCE_JOURNAL_MALFORMED in result["reason_codes"]
    assert report["rejected_annotations"] == 1
    assert report["orders_sent"] == 0


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


def accepted_annotation_journal(annotation: dict[str, str]) -> dict:
    return {
        "project": "xm-gold-ai-trader",
        "mode": "ai_signal_annotation",
        "annotation_schema_version": 1,
        "timestamp_utc": "2026-05-28T00:00:00+00:00",
        "source_journal_path": "source.json",
        "source_journal_hash": "abc",
        "source_final_decision": "BLOCK",
        "final_decision": "BLOCK",
        "annotation_status": "ACCEPTED",
        "annotation": annotation,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
    }


def write_source_journal(path, *, final_decision: str = "BLOCK") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "timestamp_utc": "2026-05-28T00:00:00+00:00",
        "final_decision": final_decision,
        "reason_codes": [] if final_decision == "SIGNAL" else ["NO_ACTIONABLE_SIGNAL"],
        "reasons": [],
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "current_spread_points": 55.0,
        "risk_preview": {"evaluated": False, "reason_codes": []},
        "signal": {"side": "HOLD"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
