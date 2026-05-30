from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


MODE = "research_pipeline_verify"

REASON_COMMAND_FAILED = "COMMAND_FAILED"
REASON_JSON_PARSE_FAILED = "JSON_PARSE_FAILED"
REASON_ORDERS_SENT_NONZERO = "ORDERS_SENT_NONZERO"
REASON_ORDER_CHECK_CALLED = "ORDER_CHECK_CALLED"
REASON_ORDER_SEND_CALLED = "ORDER_SEND_CALLED"
REASON_FORBIDDEN_AI_TRADING_CONTENT = "FORBIDDEN_AI_TRADING_CONTENT"
REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE = "MISSING_AI_ANNOTATION_AFTER_ANNOTATE"
REASON_SUBCHECK_BLOCK = "SUBCHECK_BLOCK"
REASON_SUBCHECK_WARN = "SUBCHECK_WARN"

FORBIDDEN_CONTENT_REASON_CODES = {"ANNOTATION_FORBIDDEN_FIELD"}
MISSING_ANNOTATION_REASON_CODES = {"MISSING_AI_ANNOTATION"}
SAFETY_WARNING_CODES = {
    REASON_ORDERS_SENT_NONZERO,
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_FORBIDDEN_AI_TRADING_CONTENT,
    REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE,
}
LIVE_SAMPLE_COVERAGE_WARNING_CODES = {
    "UNIQUE_CLOSED_BARS_BELOW_MINIMUM",
    "INSUFFICIENT_LIVE_SAMPLE",
}
RESEARCH_QUALITY_WARNING_CODES = {
    "LIVE_SIGNAL_COUNT_ZERO",
    "MALFORMED_LIVE_JOURNALS",
    "HISTORICAL_COMPARISON_UNAVAILABLE",
    "TOO_MANY_MALFORMED_JOURNALS",
}
STRATEGY_SIGNAL_WARNING_CODES = {
    "ZERO_ACTIONABLE_SIGNAL_RATE",
    "LOW_LIVE_SIGNAL_RATE",
    "HIGH_LIVE_SIGNAL_RATE",
}


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    command: list[str]
    returncode: int
    final_decision: str
    reason_codes: list[str]
    reasons: list[str]
    payload: dict[str, Any] | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""


def main() -> int:
    args = parse_args()
    checks = run_research_pipeline()
    report = summarize_checks(checks)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0 if report["final_decision"] != "BLOCK" else 1


def run_research_pipeline() -> list[CheckResult]:
    commands = research_pipeline_commands()
    results: list[CheckResult] = []
    for name, command in commands:
        if name == "pytest":
            results.append(run_pytest(command))
        else:
            results.append(run_json_command(name, command))
    return results


def research_pipeline_commands() -> list[tuple[str, list[str]]]:
    return [
        ("pytest", [sys.executable, "-m", "pytest"]),
        (
            "evaluate_dry_run_observation_quality",
            [sys.executable, "scripts/evaluate_dry_run_observation_quality.py", "--json"],
        ),
        (
            "compare_live_vs_historical_signal_rate",
            [sys.executable, "scripts/compare_live_vs_historical_signal_rate.py", "--json"],
        ),
        (
            "analyze_live_sample_quality",
            [sys.executable, "scripts/analyze_live_sample_quality.py", "--json"],
        ),
        (
            "annotate_dry_run_signals",
            [sys.executable, "scripts/annotate_dry_run_signals.py", "--mock-ai", "--json"],
        ),
        ("audit_ai_annotations", [sys.executable, "scripts/audit_ai_annotations.py", "--json"]),
        ("ai_annotation_report", [sys.executable, "scripts/ai_annotation_report.py", "--json"]),
        (
            "analyze_ai_annotations_vs_signals",
            [sys.executable, "scripts/analyze_ai_annotations_vs_signals.py", "--json"],
        ),
    ]


def run_pytest(command: list[str]) -> CheckResult:
    completed = run_command(command)
    if completed.returncode == 0:
        return CheckResult(
            name="pytest",
            command=command,
            returncode=completed.returncode,
            final_decision="PASS",
            reason_codes=[],
            reasons=[],
            stdout_tail=tail(completed.stdout),
            stderr_tail=tail(completed.stderr),
        )
    return CheckResult(
        name="pytest",
        command=command,
        returncode=completed.returncode,
        final_decision="BLOCK",
        reason_codes=[REASON_COMMAND_FAILED],
        reasons=[f"{REASON_COMMAND_FAILED}: pytest returned {completed.returncode}"],
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )


def run_json_command(name: str, command: list[str]) -> CheckResult:
    completed = run_command(command)
    reason_codes: list[str] = []
    reasons: list[str] = []
    if completed.returncode != 0:
        reason_codes.append(REASON_COMMAND_FAILED)
        reasons.append(f"{REASON_COMMAND_FAILED}: {name} returned {completed.returncode}")

    try:
        payload = parse_json_object(completed.stdout)
    except ValueError as exc:
        reason_codes.append(REASON_JSON_PARSE_FAILED)
        reasons.append(f"{REASON_JSON_PARSE_FAILED}: {exc}")
        return CheckResult(
            name=name,
            command=command,
            returncode=completed.returncode,
            final_decision="BLOCK",
            reason_codes=dedupe(reason_codes),
            reasons=reasons,
            payload=None,
            stdout_tail=tail(completed.stdout),
            stderr_tail=tail(completed.stderr),
        )

    safety_codes, safety_reasons = validate_payload_safety(name, payload)
    reason_codes.extend(safety_codes)
    reasons.extend(safety_reasons)

    if any(code in blocking_reason_codes() for code in reason_codes):
        final_decision = "BLOCK"
    elif payload_warns(payload):
        final_decision = "WARN"
        if REASON_SUBCHECK_WARN not in reason_codes:
            reason_codes.append(REASON_SUBCHECK_WARN)
            reasons.append(f"{REASON_SUBCHECK_WARN}: {name} reported a warning condition")
    else:
        final_decision = "PASS"

    return CheckResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        final_decision=final_decision,
        reason_codes=dedupe(reason_codes),
        reasons=reasons,
        payload=payload,
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
    )


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_json_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"no JSON object found in stdout: {output[:500]!r}")


def validate_payload_safety(name: str, payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    codes: list[str] = []
    reasons: list[str] = []
    for path, key, value in walk_json(payload):
        if is_orders_sent_key(key) and numeric_value(value) > 0:
            codes.append(REASON_ORDERS_SENT_NONZERO)
            reasons.append(f"{REASON_ORDERS_SENT_NONZERO}: {name}.{path} is {value!r}")
        if "order_check_called" in key and safety_flag_is_set(value):
            codes.append(REASON_ORDER_CHECK_CALLED)
            reasons.append(f"{REASON_ORDER_CHECK_CALLED}: {name}.{path} is {value!r}")
        if "order_send_called" in key and safety_flag_is_set(value):
            codes.append(REASON_ORDER_SEND_CALLED)
            reasons.append(f"{REASON_ORDER_SEND_CALLED}: {name}.{path} is {value!r}")
        if key in {"forbidden_violations", "forbidden_field_violations"} and numeric_value(value) > 0:
            codes.append(REASON_FORBIDDEN_AI_TRADING_CONTENT)
            reasons.append(f"{REASON_FORBIDDEN_AI_TRADING_CONTENT}: {name}.{path} is {value!r}")

    reason_codes = set(str(code) for code in payload.get("reason_codes") or [])
    reason_count_codes = set((payload.get("reason_code_counts") or {}).keys())
    all_payload_codes = reason_codes | reason_count_codes
    if all_payload_codes.intersection(FORBIDDEN_CONTENT_REASON_CODES):
        codes.append(REASON_FORBIDDEN_AI_TRADING_CONTENT)
        reasons.append(f"{REASON_FORBIDDEN_AI_TRADING_CONTENT}: {name} reported forbidden annotation content")
    if name == "analyze_ai_annotations_vs_signals" and all_payload_codes.intersection(MISSING_ANNOTATION_REASON_CODES):
        codes.append(REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE)
        reasons.append(f"{REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE}: missing annotations remain after annotation step")
    if payload.get("final_decision") == "BLOCK":
        codes.append(REASON_SUBCHECK_BLOCK)
        reasons.append(f"{REASON_SUBCHECK_BLOCK}: {name} reported final_decision BLOCK")
    return dedupe(codes), reasons


def walk_json(value: Any, prefix: str = "") -> list[tuple[str, str, Any]]:
    items: list[tuple[str, str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            items.append((path, str(key), child))
            items.extend(walk_json(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = f"{prefix}[{index}]"
            items.extend(walk_json(child, path))
    return items


def is_orders_sent_key(key: str) -> bool:
    return key == "orders_sent" or key.endswith("orders_sent_sum")


def numeric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safety_flag_is_set(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return numeric_value(value) > 0


def payload_warns(payload: dict[str, Any]) -> bool:
    if payload.get("final_decision") == "WARN":
        return True
    if payload.get("expectation_result") in {"LOW_SIGNAL_WARNING", "HIGH_SIGNAL_WARNING"}:
        return True
    reason_codes = set(str(code) for code in payload.get("reason_codes") or [])
    return "INSUFFICIENT_LIVE_SAMPLE" in reason_codes


def summarize_checks(checks: list[CheckResult]) -> dict[str, Any]:
    reason_counter: dict[str, int] = {}
    reasons: list[str] = []
    for check in checks:
        for code in check.reason_codes:
            reason_counter[code] = reason_counter.get(code, 0) + 1
        reasons.extend(check.reasons)
    if any(check.final_decision == "BLOCK" for check in checks):
        final_decision = "BLOCK"
    elif any(check.final_decision == "WARN" for check in checks):
        final_decision = "WARN"
    else:
        final_decision = "PASS"
    live_sample_coverage = summarize_live_sample_coverage(checks)
    warning_taxonomy = categorize_warnings(checks, live_sample_coverage)
    for category in warning_taxonomy["categories"].values():
        for code in category["reason_codes"]:
            if code not in reason_counter:
                reason_counter[code] = 1
    return {
        "project": "xm-gold-ai-trader",
        "mode": MODE,
        "final_decision": final_decision,
        "reason_codes": sorted(reason_counter),
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "reasons": reasons,
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "live_sample_coverage": live_sample_coverage,
        "warning_taxonomy": warning_taxonomy,
        "safety_warnings": warning_taxonomy["categories"]["safety_warnings"],
        "live_sample_coverage_warnings": warning_taxonomy["categories"]["live_sample_coverage_warnings"],
        "research_quality_warnings": warning_taxonomy["categories"]["research_quality_warnings"],
        "strategy_signal_warnings": warning_taxonomy["categories"]["strategy_signal_warnings"],
        "checks": [
            {
                "name": check.name,
                "command": command_display(check.command),
                "returncode": check.returncode,
                "final_decision": check.final_decision,
                "reason_codes": check.reason_codes,
                "reasons": check.reasons,
                "payload_final_decision": check.payload.get("final_decision") if check.payload else None,
                "payload_reason_codes": check.payload.get("reason_codes") if check.payload else None,
                "orders_sent": check.payload.get("orders_sent") if check.payload else 0,
                "order_check_called": check.payload.get("order_check_called") if check.payload else False,
                "order_send_called": check.payload.get("order_send_called") if check.payload else False,
                "live_sample_coverage": check.payload.get("live_sample_coverage") if check.payload else None,
            }
            for check in checks
        ],
    }


def summarize_live_sample_coverage(checks: list[CheckResult]) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    warn_codes: list[str] = []
    for check in checks:
        if not check.payload:
            continue
        coverage = check.payload.get("live_sample_coverage")
        if not isinstance(coverage, dict):
            continue
        source = {
            "check_name": check.name,
            "source_name": coverage.get("source_name"),
            "source_path": coverage.get("source_path"),
            "source_glob": coverage.get("source_glob"),
            "current_unique_closed_bars": coverage.get("current_unique_closed_bars"),
            "required_min_unique_closed_bars": coverage.get("required_min_unique_closed_bars"),
            "sufficient_closed_bar_coverage": coverage.get("sufficient_closed_bar_coverage"),
            "warn_reason_codes": list(coverage.get("warn_reason_codes") or []),
        }
        sources.append(source)
        warn_codes.extend(
            code
            for code in source["warn_reason_codes"]
            if code in LIVE_SAMPLE_COVERAGE_WARNING_CODES
        )
    current_values = [
        int(source["current_unique_closed_bars"])
        for source in sources
        if source.get("current_unique_closed_bars") is not None
    ]
    required_values = [
        int(source["required_min_unique_closed_bars"])
        for source in sources
        if source.get("required_min_unique_closed_bars") is not None
    ]
    return {
        "source_name": "dry_run_signal_journals",
        "source_path": first_present([source.get("source_path") for source in sources]),
        "source_glob": first_present([source.get("source_glob") for source in sources]),
        "current_unique_closed_bars": min(current_values) if current_values else None,
        "required_min_unique_closed_bars": max(required_values) if required_values else None,
        "sufficient_closed_bar_coverage": all(
            bool(source.get("sufficient_closed_bar_coverage")) for source in sources
        ) if sources else None,
        "warn_reason_codes": dedupe(warn_codes),
        "sources": sources,
    }


def categorize_warnings(checks: list[CheckResult], live_sample_coverage: dict[str, Any]) -> dict[str, Any]:
    details = warning_details(checks, live_sample_coverage)
    categories = {
        "safety_warnings": build_warning_category(
            details=details,
            codes=SAFETY_WARNING_CODES,
            safety_violation=True,
            description="Order execution, order-check, order-send, or forbidden AI trading boundary warnings.",
        ),
        "live_sample_coverage_warnings": build_warning_category(
            details=details,
            codes=LIVE_SAMPLE_COVERAGE_WARNING_CODES,
            safety_violation=False,
            description="Warnings about insufficient dry-run closed-bar sample coverage.",
        ),
        "research_quality_warnings": build_warning_category(
            details=details,
            codes=RESEARCH_QUALITY_WARNING_CODES,
            safety_violation=False,
            description="Read-only research data quality warnings that do not imply order execution.",
        ),
        "strategy_signal_warnings": build_warning_category(
            details=details,
            codes=STRATEGY_SIGNAL_WARNING_CODES,
            safety_violation=False,
            description="Read-only baseline strategy signal-quality warnings, not safety violations.",
        ),
    }
    categorized_codes = [
        code
        for category in categories.values()
        for code in category["reason_codes"]
    ]
    uncategorized = [
        detail
        for code, detail in sorted(details.items())
        if code not in categorized_codes and code != REASON_SUBCHECK_WARN
    ]
    return {
        "safety_clean": len(categories["safety_warnings"]["reason_codes"]) == 0,
        "zero_actionable_signal_rate_is_safety_violation": False,
        "categories": categories,
        "uncategorized_warnings": uncategorized,
    }


def warning_details(checks: list[CheckResult], live_sample_coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    details: dict[str, dict[str, Any]] = {}
    for code in live_sample_coverage.get("warn_reason_codes") or []:
        add_warning_detail(details, code, "live_sample_coverage", "live_sample_coverage.warn_reason_codes")
    for check in checks:
        for code in check.reason_codes:
            add_warning_detail(details, code, check.name, "check.reason_codes")
        if not check.payload:
            continue
        for code in check.payload.get("reason_codes") or []:
            add_warning_detail(details, str(code), check.name, "payload.reason_codes")
        for code in (check.payload.get("reason_code_counts") or {}).keys():
            add_warning_detail(details, str(code), check.name, "payload.reason_code_counts")
        coverage = check.payload.get("live_sample_coverage")
        if isinstance(coverage, dict):
            for code in coverage.get("warn_reason_codes") or []:
                add_warning_detail(details, str(code), check.name, "payload.live_sample_coverage.warn_reason_codes")
    return details


def add_warning_detail(details: dict[str, dict[str, Any]], code: str, check_name: str, source: str) -> None:
    if code == "LIVE_SIGNAL_RATE_WITHIN_EXPECTATION":
        return
    if source.startswith("payload") or source == "live_sample_coverage.warn_reason_codes":
        if not is_known_warning_code(code):
            return
    detail = details.setdefault(
        code,
        {
            "reason_code": code,
            "checks": [],
            "sources": [],
        },
    )
    if check_name not in detail["checks"]:
        detail["checks"].append(check_name)
    if source not in detail["sources"]:
        detail["sources"].append(source)


def is_known_warning_code(code: str) -> bool:
    return code in (
        SAFETY_WARNING_CODES
        | LIVE_SAMPLE_COVERAGE_WARNING_CODES
        | RESEARCH_QUALITY_WARNING_CODES
        | STRATEGY_SIGNAL_WARNING_CODES
        | {REASON_SUBCHECK_WARN, REASON_COMMAND_FAILED, REASON_JSON_PARSE_FAILED, REASON_SUBCHECK_BLOCK}
    )


def build_warning_category(
    *,
    details: dict[str, dict[str, Any]],
    codes: set[str],
    safety_violation: bool,
    description: str,
) -> dict[str, Any]:
    selected = [
        details[code]
        for code in sorted(codes)
        if code in details
    ]
    return {
        "reason_codes": [item["reason_code"] for item in selected],
        "count": len(selected),
        "safety_violation": safety_violation and bool(selected),
        "description": description,
        "details": selected,
    }


def first_present(values: list[Any]) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def blocking_reason_codes() -> set[str]:
    return {
        REASON_COMMAND_FAILED,
        REASON_JSON_PARSE_FAILED,
        REASON_ORDERS_SENT_NONZERO,
        REASON_ORDER_CHECK_CALLED,
        REASON_ORDER_SEND_CALLED,
        REASON_FORBIDDEN_AI_TRADING_CONTENT,
        REASON_MISSING_AI_ANNOTATION_AFTER_ANNOTATE,
        REASON_SUBCHECK_BLOCK,
    }


def command_display(command: list[str]) -> str:
    return " ".join(command)


def dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output


def tail(value: str, limit: int = 2000) -> str:
    return value[-limit:] if value else ""


def print_summary(report: dict[str, Any]) -> None:
    print("xm-gold-ai-trader research pipeline verification")
    print(f"final_decision: {report['final_decision']}")
    for check in report["checks"]:
        print(f"{check['name']}: {check['final_decision']}")
    print("orders_sent: 0")


def parse_args() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="Verify the read-only research pipeline end to end.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
