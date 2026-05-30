from __future__ import annotations

from scripts.research_pipeline_verify import (
    CheckResult,
    REASON_FORBIDDEN_AI_TRADING_CONTENT,
    REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE,
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
    REASON_SUBCHECK_WARN,
    parse_json_object,
    research_pipeline_commands,
    summarize_checks,
    summarize_live_sample_coverage,
    validate_payload_safety,
)


def test_parse_json_object_with_prefix_logs():
    payload = parse_json_object("2026 info line\n{\"orders_sent\": 0, \"final_decision\": \"PASS\"}\n")

    assert payload == {"orders_sent": 0, "final_decision": "PASS"}


def test_safety_aggregation_blocks_orders_sent():
    codes, _reasons = validate_payload_safety("sample", {"orders_sent": 1})

    assert REASON_ORDERS_SENT_NONZERO in codes


def test_safety_aggregation_blocks_order_check_and_send_counts():
    payload = {
        "order_check_called_count": 1,
        "nested": {"observed_order_send_called_count": 2},
        "orders_sent": 0,
    }

    codes, _reasons = validate_payload_safety("sample", payload)

    assert REASON_ORDER_CHECK_CALLED in codes
    assert REASON_ORDER_SEND_CALLED in codes


def test_safety_aggregation_blocks_forbidden_ai_content():
    payload = {"forbidden_violations": 1, "reason_codes": ["ANNOTATION_FORBIDDEN_FIELD"], "orders_sent": 0}

    codes, _reasons = validate_payload_safety("sample", payload)

    assert REASON_FORBIDDEN_AI_TRADING_CONTENT in codes


def test_missing_annotations_after_annotate_blocks_pipeline_analysis():
    payload = {"final_decision": "WARN", "reason_codes": ["MISSING_AI_ANNOTATION"], "orders_sent": 0}

    codes, _reasons = validate_payload_safety("analyze_ai_annotations_vs_signals", payload)

    assert REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE in codes


def test_summary_allows_insufficient_sample_as_warn_not_block():
    checks = [
        CheckResult(
            name="compare",
            command=["python", "script.py"],
            returncode=0,
            final_decision="WARN",
            reason_codes=[REASON_SUBCHECK_WARN],
            reasons=["INSUFFICIENT_LIVE_SAMPLE"],
            payload={
                "orders_sent": 0,
                "reason_codes": ["INSUFFICIENT_LIVE_SAMPLE"],
                "live_sample_coverage": {
                    "source_name": "dry_run_signal_journals",
                    "source_path": "logs/dry_run_signals",
                    "source_glob": "logs/dry_run_signals/*.json",
                    "current_unique_closed_bars": 29,
                    "required_min_unique_closed_bars": 100,
                    "sufficient_closed_bar_coverage": False,
                    "warn_reason_codes": ["INSUFFICIENT_LIVE_SAMPLE"],
                },
            },
        )
    ]

    report = summarize_checks(checks)

    assert report["final_decision"] == "WARN"
    assert report["orders_sent"] == 0
    assert report["live_sample_coverage"]["current_unique_closed_bars"] == 29
    assert report["live_sample_coverage"]["required_min_unique_closed_bars"] == 100
    assert report["live_sample_coverage"]["warn_reason_codes"] == ["INSUFFICIENT_LIVE_SAMPLE"]
    assert report["live_sample_coverage_warnings"]["reason_codes"] == ["INSUFFICIENT_LIVE_SAMPLE"]
    assert report["safety_warnings"]["reason_codes"] == []


def test_sufficient_sample_coverage_clears_sample_warns():
    checks = [
        CheckResult(
            name="quality",
            command=["python", "quality.py"],
            returncode=0,
            final_decision="PASS",
            reason_codes=[],
            reasons=[],
            payload={
                "orders_sent": 0,
                "live_sample_coverage": {
                    "source_name": "dry_run_signal_journals",
                    "source_path": "logs/dry_run_signals",
                    "source_glob": "logs/dry_run_signals/*.json",
                    "current_unique_closed_bars": 120,
                    "required_min_unique_closed_bars": 100,
                    "sufficient_closed_bar_coverage": True,
                    "warn_reason_codes": [],
                },
            },
        ),
        CheckResult(
            name="compare",
            command=["python", "compare.py"],
            returncode=0,
            final_decision="PASS",
            reason_codes=[],
            reasons=[],
            payload={
                "orders_sent": 0,
                "live_sample_coverage": {
                    "source_name": "dry_run_signal_journals",
                    "source_path": "logs/dry_run_signals",
                    "source_glob": "logs/dry_run_signals/*.json",
                    "current_unique_closed_bars": 120,
                    "required_min_unique_closed_bars": 100,
                    "sufficient_closed_bar_coverage": True,
                    "warn_reason_codes": [],
                },
            },
        ),
    ]

    report = summarize_checks(checks)

    assert report["final_decision"] == "PASS"
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is True
    assert report["live_sample_coverage"]["warn_reason_codes"] == []
    assert report["live_sample_coverage_warnings"]["reason_codes"] == []
    assert report["safety_warnings"]["reason_codes"] == []


def test_live_sample_coverage_summary_uses_explicit_sources():
    coverage = summarize_live_sample_coverage(
        [
            CheckResult(
                name="quality",
                command=["python", "quality.py"],
                returncode=0,
                final_decision="WARN",
                reason_codes=[REASON_SUBCHECK_WARN],
                reasons=[],
                payload={
                    "live_sample_coverage": {
                        "source_name": "dry_run_signal_journals",
                        "source_path": "logs/dry_run_signals",
                        "source_glob": "logs/dry_run_signals/*.json",
                        "current_unique_closed_bars": 42,
                        "required_min_unique_closed_bars": 100,
                        "sufficient_closed_bar_coverage": False,
                        "warn_reason_codes": ["UNIQUE_CLOSED_BARS_BELOW_MINIMUM"],
                    }
                },
            )
        ]
    )

    assert coverage["source_name"] == "dry_run_signal_journals"
    assert coverage["source_path"] == "logs/dry_run_signals"
    assert coverage["current_unique_closed_bars"] == 42
    assert coverage["required_min_unique_closed_bars"] == 100
    assert coverage["warn_reason_codes"] == ["UNIQUE_CLOSED_BARS_BELOW_MINIMUM"]


def test_research_pipeline_includes_live_sample_quality_analysis():
    names = [name for name, _command in research_pipeline_commands()]

    assert "analyze_live_sample_quality" in names
    assert names.index("analyze_live_sample_quality") > names.index("compare_live_vs_historical_signal_rate")


def test_safety_violations_are_categorized_separately():
    checks = [
        CheckResult(
            name="unsafe",
            command=["python", "unsafe.py"],
            returncode=0,
            final_decision="BLOCK",
            reason_codes=[REASON_ORDERS_SENT_NONZERO, REASON_ORDER_CHECK_CALLED],
            reasons=[],
            payload={"orders_sent": 1, "order_check_called": True},
        )
    ]

    report = summarize_checks(checks)

    assert report["final_decision"] == "BLOCK"
    assert report["warning_taxonomy"]["safety_clean"] is False
    assert report["safety_warnings"]["safety_violation"] is True
    assert set(report["safety_warnings"]["reason_codes"]) == {
        REASON_ORDERS_SENT_NONZERO,
        REASON_ORDER_CHECK_CALLED,
    }
    assert report["live_sample_coverage_warnings"]["reason_codes"] == []


def test_zero_actionable_signal_rate_is_strategy_signal_warning_not_safety():
    checks = [
        CheckResult(
            name="evaluate_dry_run_observation_quality",
            command=["python", "quality.py"],
            returncode=0,
            final_decision="WARN",
            reason_codes=[REASON_SUBCHECK_WARN],
            reasons=[],
            payload={
                "orders_sent": 0,
                "reason_codes": ["ZERO_ACTIONABLE_SIGNAL_RATE"],
                "live_sample_coverage": {
                    "source_name": "dry_run_signal_journals",
                    "source_path": "logs/dry_run_signals",
                    "source_glob": "logs/dry_run_signals/*.json",
                    "current_unique_closed_bars": 121,
                    "required_min_unique_closed_bars": 100,
                    "sufficient_closed_bar_coverage": True,
                    "warn_reason_codes": ["ZERO_ACTIONABLE_SIGNAL_RATE"],
                },
            },
        ),
        CheckResult(
            name="analyze_live_sample_quality",
            command=["python", "analyze.py"],
            returncode=0,
            final_decision="WARN",
            reason_codes=[REASON_SUBCHECK_WARN],
            reasons=[],
            payload={
                "orders_sent": 0,
                "order_check_called": False,
                "order_send_called": False,
                "final_decision": "WARN",
                "reason_codes": ["LIVE_SIGNAL_COUNT_ZERO"],
            },
        ),
    ]

    report = summarize_checks(checks)

    assert report["final_decision"] == "WARN"
    assert report["warning_taxonomy"]["safety_clean"] is True
    assert report["warning_taxonomy"]["zero_actionable_signal_rate_is_safety_violation"] is False
    assert report["safety_warnings"]["reason_codes"] == []
    assert report["live_sample_coverage"]["sufficient_closed_bar_coverage"] is True
    assert report["live_sample_coverage_warnings"]["reason_codes"] == []
    assert report["strategy_signal_warnings"]["reason_codes"] == ["ZERO_ACTIONABLE_SIGNAL_RATE"]
    assert report["strategy_signal_warnings"]["safety_violation"] is False
    assert report["research_quality_warnings"]["reason_codes"] == ["LIVE_SIGNAL_COUNT_ZERO"]
