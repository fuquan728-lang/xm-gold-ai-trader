from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.compare_live_vs_historical_signal_rate import (
    DEFAULT_HISTORICAL_REPORT,
    compare_live_vs_historical,
    load_or_build_historical_report,
)
from scripts.dry_run_campaign_report import DEFAULT_CAMPAIGN_DIR, load_campaign_metadata
from scripts.dry_run_signal_report import (
    DEFAULT_JOURNAL_DIR,
    load_dry_run_journals,
    numeric_or_none,
)
from scripts.evaluate_dry_run_observation_quality import (
    REASON_ORDER_CHECK_CALLED,
    REASON_ORDER_SEND_CALLED,
    REASON_ORDERS_SENT_NONZERO,
    unique_closed_bar_observations,
)
from scripts.live_dry_run_signal_journal import DEFAULT_PARAMETER_REPORT, PROJECT


MODE = "live_sample_quality_analysis"

REASON_NO_VALID_LIVE_JOURNALS = "NO_VALID_LIVE_JOURNALS"
REASON_LIVE_SIGNAL_COUNT_ZERO = "LIVE_SIGNAL_COUNT_ZERO"
REASON_MALFORMED_LIVE_JOURNALS = "MALFORMED_LIVE_JOURNALS"
REASON_HISTORICAL_COMPARISON_UNAVAILABLE = "HISTORICAL_COMPARISON_UNAVAILABLE"
REASON_BLOCK_REASON_MISSING = "BLOCK_REASON_MISSING"

DOMINANT_RULE_THRESHOLD = 0.80


def main() -> int:
    args = parse_args()
    report = analyze_live_sample_quality(
        journal_dir=Path(args.journal_dir),
        campaign_dir=Path(args.campaign_dir),
        historical_args=args,
        min_live_bars=args.min_live_bars,
        build_historical_if_missing=not args.no_build_historical,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def analyze_live_sample_quality(
    *,
    journal_dir: Path,
    campaign_dir: Path,
    historical_args: argparse.Namespace | None = None,
    min_live_bars: int = 100,
    build_historical_if_missing: bool = True,
) -> dict[str, Any]:
    journal_entries = load_dry_run_journals(journal_dir)
    campaign_entries = load_campaign_metadata(campaign_dir)

    valid_journals = [entry["payload"] for entry in journal_entries if entry["payload"] is not None]
    malformed_journals = [entry for entry in journal_entries if entry["payload"] is None]
    valid_campaigns = [entry["payload"] for entry in campaign_entries if entry["payload"] is not None]
    malformed_campaigns = [entry for entry in campaign_entries if entry["payload"] is None]
    unique_observations = unique_closed_bar_observations(valid_journals)

    live_metrics = summarize_live_observations(unique_observations)
    block_attribution = build_block_reason_attribution(unique_observations)
    candidate_forensics = build_signal_candidate_forensics(unique_observations)
    diagnostics_coverage = build_diagnostics_coverage(valid_journals)
    campaign_distribution = build_campaign_distribution(valid_journals, unique_observations, valid_campaigns)
    closed_bar_distribution = build_closed_bar_distribution(unique_observations)
    safety = scan_safety_boundaries(valid_journals, valid_campaigns)
    historical = build_historical_comparison(
        historical_args=historical_args,
        live_payloads=valid_journals,
        min_live_bars=min_live_bars,
        build_historical_if_missing=build_historical_if_missing,
    )

    reason_codes: list[str] = []
    reasons: list[str] = []
    if safety["observed_orders_sent_sum"] > 0:
        add_reason(reason_codes, reasons, REASON_ORDERS_SENT_NONZERO, "dry-run journals or campaign metadata report orders_sent > 0")
    if safety["order_check_called_count"] > 0:
        add_reason(reason_codes, reasons, REASON_ORDER_CHECK_CALLED, "dry-run journals report order_check_called true")
    if safety["order_send_called_count"] > 0:
        add_reason(reason_codes, reasons, REASON_ORDER_SEND_CALLED, "dry-run journals report order_send_called true")
    if not valid_journals:
        add_reason(reason_codes, reasons, REASON_NO_VALID_LIVE_JOURNALS, f"no valid live dry-run journals found in {journal_dir}")
    if malformed_journals or malformed_campaigns:
        add_reason(
            reason_codes,
            reasons,
            REASON_MALFORMED_LIVE_JOURNALS,
            f"malformed journals={len(malformed_journals)}, malformed campaigns={len(malformed_campaigns)}",
        )
    if live_metrics["zero_signal_across_live_samples"] and live_metrics["unique_closed_bars"] > 0:
        add_reason(reason_codes, reasons, REASON_LIVE_SIGNAL_COUNT_ZERO, "signal_count is 0 across unique live closed-bar samples")
    if not historical["available"]:
        add_reason(reason_codes, reasons, REASON_HISTORICAL_COMPARISON_UNAVAILABLE, historical["reason"])

    final_decision = "PASS"
    if any(code in reason_codes for code in (REASON_ORDERS_SENT_NONZERO, REASON_ORDER_CHECK_CALLED, REASON_ORDER_SEND_CALLED)):
        final_decision = "BLOCK"
    elif reason_codes:
        final_decision = "WARN"

    return {
        "project": PROJECT,
        "mode": MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "final_decision": final_decision,
        "reason_codes": reason_codes,
        "reasons": reasons,
        "journal_dir": str(journal_dir),
        "campaign_dir": str(campaign_dir),
        "journal_source_glob": str(journal_dir / "*.json"),
        "campaign_source_glob": str(campaign_dir / "*.json"),
        "orders_sent": 0,
        "observed_orders_sent_sum": safety["observed_orders_sent_sum"],
        "order_check_called": safety["order_check_called_count"] > 0,
        "order_send_called": safety["order_send_called_count"] > 0,
        "order_check_called_count": safety["order_check_called_count"],
        "order_send_called_count": safety["order_send_called_count"],
        "total_journals": len(journal_entries),
        "total_journal_files": len(journal_entries),
        "total_valid_journals": len(valid_journals),
        "enriched_journal_count": diagnostics_coverage["enriched_journal_count"],
        "legacy_journal_count": diagnostics_coverage["legacy_journal_count"],
        "diagnostics_field_coverage": diagnostics_coverage["diagnostics_field_coverage"],
        "sma_field_availability": diagnostics_coverage["sma_field_availability"],
        "crossover_state_availability": diagnostics_coverage["crossover_state_availability"],
        "failed_rule_field_availability": diagnostics_coverage["failed_rule_field_availability"],
        "malformed_journals": len(malformed_journals),
        "total_campaign_files": len(campaign_entries),
        "total_valid_campaigns": len(valid_campaigns),
        "malformed_campaigns": len(malformed_campaigns),
        "unique_closed_bars": live_metrics["unique_closed_bars"],
        "signal_count": live_metrics["signal_count"],
        "candidate_signal_count": live_metrics["candidate_signal_count"],
        "block_count": live_metrics["block_count"],
        "skip_count": live_metrics["skip_count"],
        "signal_rate": live_metrics["signal_rate"],
        "candidate_signal_rate": live_metrics["candidate_signal_rate"],
        "block_rate": live_metrics["block_rate"],
        "zero_signal_across_live_samples": live_metrics["zero_signal_across_live_samples"],
        "top_block_reasons": live_metrics["top_block_reasons"],
        "top_no_action_reasons": live_metrics["top_no_action_reasons"],
        "block_reason_counts": block_attribution["block_reason_counts"],
        "block_reason_percentages": block_attribution["block_reason_percentages"],
        "multi_reason_combinations": block_attribution["multi_reason_combinations"],
        "candidate_to_final_rejection": block_attribution["candidate_to_final_rejection"],
        "per_campaign_block_reason_distribution": block_attribution["per_campaign_block_reason_distribution"],
        "zero_final_signal_attribution": block_attribution["zero_final_signal_attribution"],
        "block_reason_attribution": block_attribution,
        "signal_candidate_forensics": candidate_forensics,
        "reason_code_counts": live_metrics["reason_code_counts"],
        "avg_spread": live_metrics["avg_spread"],
        "max_spread": live_metrics["max_spread"],
        "distribution_by_campaign": campaign_distribution,
        "distribution_by_closed_bar_time": closed_bar_distribution,
        "historical_comparison": historical,
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
    }


def summarize_live_observations(payloads: list[Mapping[str, Any]]) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    block_reason_counter: Counter[str] = Counter()
    no_action_reason_counter: Counter[str] = Counter()
    spreads: list[float] = []
    signal_count = 0
    block_count = 0
    skip_count = 0
    candidate_signal_count = 0

    for payload in payloads:
        final_decision = payload.get("final_decision")
        if is_candidate_signal(payload):
            candidate_signal_count += 1
        if final_decision == "SIGNAL":
            signal_count += 1
        elif final_decision == "BLOCK":
            block_count += 1
        elif final_decision == "SKIP":
            skip_count += 1

        codes = [str(code) for code in (payload.get("reason_codes") or [])]
        reason_counter.update(codes)
        if final_decision == "BLOCK":
            block_reason_counter.update(codes)
            for reason in payload.get("reasons") or []:
                text = str(reason)
                if "NO_ACTIONABLE_SIGNAL" in text:
                    no_action_reason_counter.update([text])

        spread = numeric_or_none(payload.get("current_spread_points"))
        if spread is not None:
            spreads.append(spread)

    total = len(payloads)
    return {
        "unique_closed_bars": total,
        "signal_count": signal_count,
        "candidate_signal_count": candidate_signal_count,
        "block_count": block_count,
        "skip_count": skip_count,
        "signal_rate": signal_count / total if total else 0.0,
        "candidate_signal_rate": candidate_signal_count / total if total else 0.0,
        "block_rate": block_count / total if total else 0.0,
        "zero_signal_across_live_samples": total > 0 and signal_count == 0,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "top_block_reasons": counter_to_top_list(block_reason_counter),
        "top_no_action_reasons": counter_to_top_list(no_action_reason_counter),
        "avg_spread": sum(spreads) / len(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
    }


def build_block_reason_attribution(payloads: list[Mapping[str, Any]]) -> dict[str, Any]:
    blocks = [payload for payload in payloads if payload.get("final_decision") == "BLOCK"]
    signal_count = sum(1 for payload in payloads if payload.get("final_decision") == "SIGNAL")
    candidate_signals = [payload for payload in payloads if is_candidate_signal(payload)]
    candidate_rejections = [payload for payload in candidate_signals if payload.get("final_decision") != "SIGNAL"]

    block_reason_counter = reason_counter_for(blocks)
    combination_counter = Counter(reason_combination(payload) for payload in blocks)
    candidate_rejection_counter = reason_counter_for(candidate_rejections)
    by_side: dict[str, dict[str, Any]] = {}
    for side in ("BUY", "SELL"):
        side_payloads = [payload for payload in candidate_rejections if signal_side(payload) == side]
        side_counter = reason_counter_for(side_payloads)
        by_side[side] = {
            "candidate_rejection_count": len(side_payloads),
            "reason_counts": dict(sorted(side_counter.items())),
            "reason_percentages": percentages(side_counter, len(side_payloads)),
            "top_rejection_reasons": reason_counter_to_list(side_counter, len(side_payloads)),
        }

    per_campaign = build_per_campaign_block_distribution(payloads)
    zero_attribution = classify_zero_final_signal_attribution(
        signal_count=signal_count,
        block_count=len(blocks),
        reason_counts=block_reason_counter,
    )

    return {
        "total_journals_analyzed": len(payloads),
        "unique_closed_bars": len(payloads),
        "block_count": len(blocks),
        "final_signal_count": signal_count,
        "candidate_signal_count": len(candidate_signals),
        "block_reason_counts": dict(sorted(block_reason_counter.items())),
        "block_reason_percentages": percentages(block_reason_counter, len(blocks)),
        "top_block_reasons": reason_counter_to_list(block_reason_counter, len(blocks)),
        "multi_reason_combinations": [
            {
                "reason_codes": list(codes),
                "count": count,
                "percentage": count / len(blocks) if blocks else 0.0,
            }
            for codes, count in sorted(combination_counter.items(), key=lambda item: (-item[1], item[0]))
            if len(codes) > 1
        ],
        "candidate_to_final_rejection": {
            "total_candidate_signals": len(candidate_signals),
            "final_signal_count": signal_count,
            "candidate_rejection_count": len(candidate_rejections),
            "candidate_rejection_rate": len(candidate_rejections) / len(candidate_signals) if candidate_signals else 0.0,
            "reason_counts": dict(sorted(candidate_rejection_counter.items())),
            "reason_percentages": percentages(candidate_rejection_counter, len(candidate_rejections)),
            "top_rejection_reasons": reason_counter_to_list(candidate_rejection_counter, len(candidate_rejections)),
            "by_side": by_side,
        },
        "per_campaign_block_reason_distribution": per_campaign,
        "zero_final_signal_attribution": zero_attribution,
    }


def build_signal_candidate_forensics(payloads: list[Mapping[str, Any]]) -> dict[str, Any]:
    diagnostics = [bar_diagnostics(payload) for payload in payloads]
    no_candidate_generated = sum(1 for item in diagnostics if item["candidate_direction"] is None)
    candidate_generated = len(diagnostics) - no_candidate_generated
    candidate_rejected = sum(
        1
        for item in diagnostics
        if item["candidate_direction"] is not None and item["final_decision"] != "SIGNAL"
    )
    final_signal_count = sum(1 for item in diagnostics if item["final_decision"] == "SIGNAL")
    failed_pre_signal_counter: Counter[str] = Counter()
    execution_blocker_counter: Counter[str] = Counter()
    for item in diagnostics:
        failed_pre_signal_counter.update(item["failed_pre_signal_conditions"])
        execution_blocker_counter.update(item["execution_feasibility_blockers"])

    return {
        "total_bars_analyzed": len(diagnostics),
        "no_candidate_generated": no_candidate_generated,
        "candidate_generated": candidate_generated,
        "candidate_generated_but_rejected": candidate_rejected,
        "final_signal_count": final_signal_count,
        "top_failed_pre_signal_conditions": counter_to_top_list(failed_pre_signal_counter),
        "top_execution_feasibility_blockers": counter_to_top_list(execution_blocker_counter),
        "per_bar_diagnostics": diagnostics,
    }


def build_diagnostics_coverage(payloads: list[Mapping[str, Any]]) -> dict[str, Any]:
    total = len(payloads)
    enriched = [payload for payload in payloads if isinstance(payload.get("diagnostics"), Mapping)]
    legacy_count = total - len(enriched)
    field_paths = {
        "diagnostics": ("diagnostics",),
        "fast_sma": ("diagnostics", "signal", "fast_sma"),
        "slow_sma": ("diagnostics", "signal", "slow_sma"),
        "previous_fast_sma": ("diagnostics", "signal", "previous_fast_sma"),
        "previous_slow_sma": ("diagnostics", "signal", "previous_slow_sma"),
        "sma_crossover_state": ("diagnostics", "signal", "sma_crossover_state"),
        "atr": ("diagnostics", "signal", "atr"),
        "stop_distance": ("diagnostics", "signal", "stop_distance"),
        "computed_lot": ("diagnostics", "feasibility", "computed_lot"),
        "normalized_lot": ("diagnostics", "feasibility", "normalized_lot"),
        "broker_volume_min": ("diagnostics", "feasibility", "broker_volume_min"),
        "broker_volume_step": ("diagnostics", "feasibility", "broker_volume_step"),
        "spread_points": ("diagnostics", "feasibility", "spread_points"),
        "max_allowed_spread_points": ("diagnostics", "feasibility", "max_allowed_spread_points"),
        "failed_pre_signal_rule_names": ("diagnostics", "signal", "failed_pre_signal_rule_names"),
        "failed_feasibility_rule_names": ("diagnostics", "feasibility", "failed_feasibility_rule_names"),
    }
    coverage = {
        name: coverage_for_field(payloads, path)
        for name, path in field_paths.items()
    }
    sma_fields = {
        name: coverage[name]
        for name in ("fast_sma", "slow_sma", "previous_fast_sma", "previous_slow_sma")
    }
    crossover_values = Counter(
        str(value_at_path(payload, field_paths["sma_crossover_state"]))
        for payload in payloads
        if value_at_path(payload, field_paths["sma_crossover_state"]) is not None
    )
    failed_pre_recorded = coverage["failed_pre_signal_rule_names"]["recorded_count"]
    failed_feasibility_recorded = coverage["failed_feasibility_rule_names"]["recorded_count"]
    both_failed_rule_fields = sum(
        1
        for payload in payloads
        if value_at_path(payload, field_paths["failed_pre_signal_rule_names"]) is not None
        and value_at_path(payload, field_paths["failed_feasibility_rule_names"]) is not None
    )
    return {
        "total_valid_journals": total,
        "enriched_journal_count": len(enriched),
        "legacy_journal_count": legacy_count,
        "enriched_journal_pct": len(enriched) / total if total else 0.0,
        "legacy_journal_pct": legacy_count / total if total else 0.0,
        "diagnostics_field_coverage": coverage,
        "sma_field_availability": sma_fields,
        "crossover_state_availability": {
            "recorded_count": coverage["sma_crossover_state"]["recorded_count"],
            "not_recorded_count": coverage["sma_crossover_state"]["not_recorded_count"],
            "recorded_pct": coverage["sma_crossover_state"]["recorded_pct"],
            "state_counts": dict(sorted(crossover_values.items())),
        },
        "failed_rule_field_availability": {
            "failed_pre_signal_rule_names_recorded": failed_pre_recorded,
            "failed_feasibility_rule_names_recorded": failed_feasibility_recorded,
            "both_failed_rule_fields_recorded": both_failed_rule_fields,
            "both_failed_rule_fields_recorded_pct": both_failed_rule_fields / total if total else 0.0,
        },
    }


def coverage_for_field(payloads: list[Mapping[str, Any]], path: tuple[str, ...]) -> dict[str, Any]:
    total = len(payloads)
    recorded = sum(1 for payload in payloads if value_at_path(payload, path) is not None)
    return {
        "field_path": ".".join(path),
        "recorded_count": recorded,
        "not_recorded_count": total - recorded,
        "recorded_pct": recorded / total if total else 0.0,
    }


def value_at_path(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for part in path:
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current.get(part)
    return current


def bar_diagnostics(payload: Mapping[str, Any]) -> dict[str, Any]:
    signal = payload.get("signal") if isinstance(payload.get("signal"), Mapping) else {}
    risk_preview = payload.get("risk_preview") if isinstance(payload.get("risk_preview"), Mapping) else {}
    symbol = payload.get("symbol") if isinstance(payload.get("symbol"), Mapping) else {}
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), Mapping) else {}
    candidate_direction = signal_side(payload) if signal_side(payload) in {"BUY", "SELL"} else None
    failed_pre_signal_conditions = failed_pre_signal_conditions_for(signal, diagnostics)
    execution_blockers = execution_blockers_for(payload, diagnostics)
    risk_lot = lot_forensics(risk_preview, symbol, diagnostics)
    indicator_values = signal_indicator_values(payload, signal, risk_preview, symbol, diagnostics)
    symbol_constraints = symbol_constraints_for(symbol, risk_preview, diagnostics)
    return {
        "timestamp_utc": payload.get("timestamp_utc"),
        "campaign_id": payload.get("campaign_id"),
        "latest_closed_bar_time": payload.get("latest_closed_bar_time"),
        "final_decision": payload.get("final_decision"),
        "candidate_direction": candidate_direction,
        "signal_side": signal.get("side"),
        "confidence": signal.get("confidence"),
        "signal_reason": signal.get("reason"),
        "failed_rule_names": sorted(set(failed_pre_signal_conditions + execution_blockers)),
        "failed_pre_signal_conditions": failed_pre_signal_conditions,
        "execution_feasibility_blockers": execution_blockers,
        "indicator_values": indicator_values,
        "risk_lot_forensics": risk_lot,
        "symbol_constraints": symbol_constraints,
        "reason_codes": list(payload.get("reason_codes") or []),
        "reasons": list(payload.get("reasons") or []),
    }


def failed_pre_signal_conditions_for(signal: Mapping[str, Any], diagnostics: Mapping[str, Any] | None = None) -> list[str]:
    if diagnostics:
        direct = diagnostics.get("failed_pre_signal_rule_names")
        if isinstance(direct, list):
            return [str(item) for item in direct]
        signal_diag = diagnostics.get("signal")
        if isinstance(signal_diag, Mapping) and isinstance(signal_diag.get("failed_pre_signal_rule_names"), list):
            return [str(item) for item in signal_diag["failed_pre_signal_rule_names"]]
    side = signal.get("side")
    reason = str(signal.get("reason") or "").lower()
    if side in {"BUY", "SELL"}:
        return []
    if "no crossover" in reason:
        return ["SMA_CROSSOVER_NOT_PRESENT"]
    if "not enough bars" in reason:
        return ["INSUFFICIENT_BARS_FOR_BASELINE"]
    if "indicator warmup" in reason:
        return ["INDICATOR_WARMUP"]
    if reason:
        return [f"BASELINE_HOLD_{reason.upper().replace(' ', '_')}"]
    return ["BASELINE_HOLD_REASON_UNAVAILABLE"]


def execution_blockers_for(payload: Mapping[str, Any], diagnostics: Mapping[str, Any] | None = None) -> list[str]:
    if diagnostics:
        direct = diagnostics.get("failed_feasibility_rule_names")
        if isinstance(direct, list):
            return sorted({str(item) for item in direct})
        feasibility = diagnostics.get("feasibility")
        if isinstance(feasibility, Mapping) and isinstance(feasibility.get("failed_feasibility_rule_names"), list):
            return sorted({str(item) for item in feasibility["failed_feasibility_rule_names"]})
    signal = payload.get("signal") if isinstance(payload.get("signal"), Mapping) else {}
    risk_preview = payload.get("risk_preview") if isinstance(payload.get("risk_preview"), Mapping) else {}
    blockers: list[str] = []
    if signal.get("side") in {"BUY", "SELL"} and payload.get("final_decision") != "SIGNAL":
        blockers.extend(str(code) for code in (risk_preview.get("reason_codes") or []))
        if not blockers:
            blockers.extend(
                str(code)
                for code in (payload.get("reason_codes") or [])
                if str(code) != "NO_ACTIONABLE_SIGNAL"
            )
    return sorted(set(blockers))


def lot_forensics(
    risk_preview: Mapping[str, Any],
    symbol: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    feasibility = diagnostics.get("feasibility") if isinstance(diagnostics, Mapping) else None
    if not isinstance(feasibility, Mapping):
        feasibility = {}
    risk_amount = numeric_or_none(risk_preview.get("risk_amount"))
    risk_per_lot = numeric_or_none(risk_preview.get("risk_per_lot"))
    if risk_amount is None:
        risk_amount = numeric_or_none(feasibility.get("risk_amount"))
    if risk_per_lot is None:
        risk_per_lot = numeric_or_none(feasibility.get("risk_per_lot"))
    computed_lot = numeric_or_none(feasibility.get("computed_lot"))
    if computed_lot is None:
        computed_lot = risk_amount / risk_per_lot if risk_amount is not None and risk_per_lot and risk_per_lot > 0 else None
    normalized_lot = numeric_or_none(feasibility.get("normalized_lot"))
    if normalized_lot is None:
        normalized_lot = numeric_or_none(risk_preview.get("volume"))
    volume_min = numeric_or_none(feasibility.get("broker_volume_min"))
    if volume_min is None:
        volume_min = numeric_or_none(symbol.get("volume_min"))
    volume_step = numeric_or_none(feasibility.get("broker_volume_step"))
    if volume_step is None:
        volume_step = numeric_or_none(symbol.get("volume_step"))
    volume_max = numeric_or_none(feasibility.get("broker_volume_max"))
    if volume_max is None:
        volume_max = numeric_or_none(symbol.get("volume_max"))
    min_lot_risk_amount = (
        volume_min * risk_per_lot if volume_min is not None and risk_per_lot is not None else None
    )
    risk_shortfall_to_min_lot = (
        min_lot_risk_amount - risk_amount
        if min_lot_risk_amount is not None and risk_amount is not None
        else None
    )
    return {
        "evaluated": bool(risk_preview.get("evaluated")),
        "lot_below_minimum": bool(risk_preview.get("lot_below_minimum")),
        "risk_amount": risk_amount,
        "risk_per_lot": risk_per_lot,
        "computed_lot": computed_lot,
        "normalized_lot": normalized_lot,
        "volume_min": volume_min,
        "volume_step": volume_step,
        "volume_max": volume_max,
        "min_lot_risk_amount": min_lot_risk_amount,
        "risk_shortfall_to_min_lot": risk_shortfall_to_min_lot,
        "reason_codes": list(risk_preview.get("reason_codes") or []),
    }


def signal_indicator_values(
    payload: Mapping[str, Any],
    signal: Mapping[str, Any],
    risk_preview: Mapping[str, Any],
    symbol: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parameters = payload.get("selected_parameters") if isinstance(payload.get("selected_parameters"), Mapping) else {}
    signal_diag = diagnostics.get("signal") if isinstance(diagnostics, Mapping) else None
    if not isinstance(signal_diag, Mapping):
        signal_diag = {}
    point = numeric_or_none(symbol.get("point"))
    entry = numeric_or_none(signal.get("entry_price"))
    stop = numeric_or_none(signal.get("stop_loss_price"))
    stop_distance_points = numeric_or_none(signal_diag.get("stop_distance_points"))
    if stop_distance_points is None:
        stop_distance_points = numeric_or_none(risk_preview.get("stop_distance_points"))
    atr_multiplier = numeric_or_none(parameters.get("atr_stop_multiplier"))
    recorded_atr = numeric_or_none(signal_diag.get("atr"))
    reconstructed_atr_price = None
    reconstructed_atr_points = None
    if entry is not None and stop is not None and atr_multiplier and atr_multiplier > 0:
        reconstructed_atr_price = abs(entry - stop) / atr_multiplier
        if point and point > 0:
            reconstructed_atr_points = reconstructed_atr_price / point
    atr_value = recorded_atr if recorded_atr is not None else reconstructed_atr_price
    atr_availability = "recorded_in_journal" if recorded_atr is not None else (
        "reconstructed_from_signal_stop_distance" if reconstructed_atr_price is not None else "not_recorded_in_journal"
    )
    return {
        "source": "live_dry_run_signal_journal",
        "availability": {
            "fast_sma": availability_for(signal_diag, "fast_sma"),
            "slow_sma": availability_for(signal_diag, "slow_sma"),
            "previous_fast_sma": availability_for(signal_diag, "previous_fast_sma"),
            "previous_slow_sma": availability_for(signal_diag, "previous_slow_sma"),
            "sma_crossover_state": availability_for(signal_diag, "sma_crossover_state"),
            "atr": atr_availability,
        },
        "selected_parameters": dict(parameters),
        "fast_sma": numeric_or_none(signal_diag.get("fast_sma")),
        "slow_sma": numeric_or_none(signal_diag.get("slow_sma")),
        "previous_fast_sma": numeric_or_none(signal_diag.get("previous_fast_sma")),
        "previous_slow_sma": numeric_or_none(signal_diag.get("previous_slow_sma")),
        "sma_crossover_state": signal_diag.get("sma_crossover_state"),
        "atr": atr_value,
        "atr_price_reconstructed": reconstructed_atr_price,
        "atr_points_reconstructed": reconstructed_atr_points,
        "stop_distance_points": stop_distance_points,
        "entry_price": entry,
        "stop_loss_price": stop,
        "take_profit_price": numeric_or_none(signal.get("take_profit_price")),
    }


def availability_for(signal_diag: Mapping[str, Any], field: str) -> str:
    if field not in signal_diag:
        return "not_recorded_in_journal"
    return "recorded_in_journal" if signal_diag.get(field) is not None else "not_recorded_in_journal"


def symbol_constraints_for(
    symbol: Mapping[str, Any],
    risk_preview: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    spread_filter = risk_preview.get("spread_filter") if isinstance(risk_preview.get("spread_filter"), Mapping) else {}
    feasibility = diagnostics.get("feasibility") if isinstance(diagnostics, Mapping) else None
    if not isinstance(feasibility, Mapping):
        feasibility = {}
    current_spread = numeric_or_none(feasibility.get("spread_points"))
    if current_spread is None:
        current_spread = numeric_or_none(spread_filter.get("current_spread_points"))
    max_spread = numeric_or_none(feasibility.get("max_allowed_spread_points"))
    if max_spread is None:
        max_spread = numeric_or_none(spread_filter.get("max_spread_points"))
    return {
        "name": symbol.get("name"),
        "point": numeric_or_none(symbol.get("point")),
        "trade_tick_size": numeric_or_none(symbol.get("trade_tick_size")),
        "trade_tick_value": numeric_or_none(symbol.get("trade_tick_value")),
        "volume_min": numeric_or_none(feasibility.get("broker_volume_min")) or numeric_or_none(symbol.get("volume_min")),
        "volume_step": numeric_or_none(feasibility.get("broker_volume_step")) or numeric_or_none(symbol.get("volume_step")),
        "volume_max": numeric_or_none(feasibility.get("broker_volume_max")) or numeric_or_none(symbol.get("volume_max")),
        "trade_stops_level": symbol.get("trade_stops_level"),
        "spread": symbol.get("spread"),
        "current_spread_points": current_spread,
        "max_spread_points": max_spread,
        "spread_allowed": feasibility.get("spread_allowed", spread_filter.get("allowed")),
    }


def build_per_campaign_block_distribution(payloads: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for payload in payloads:
        grouped[campaign_key(payload)].append(payload)

    distribution: list[dict[str, Any]] = []
    for campaign_id in sorted(grouped):
        group = grouped[campaign_id]
        blocks = [payload for payload in group if payload.get("final_decision") == "BLOCK"]
        signal_count = sum(1 for payload in group if payload.get("final_decision") == "SIGNAL")
        candidate_signals = [payload for payload in group if is_candidate_signal(payload)]
        candidate_rejections = [payload for payload in candidate_signals if payload.get("final_decision") != "SIGNAL"]
        block_counter = reason_counter_for(blocks)
        rejection_counter = reason_counter_for(candidate_rejections)
        distribution.append(
            {
                "campaign_id": None if campaign_id == "__no_campaign__" else campaign_id,
                "unique_closed_bars": len(group),
                "block_count": len(blocks),
                "final_signal_count": signal_count,
                "candidate_signal_count": len(candidate_signals),
                "candidate_rejection_count": len(candidate_rejections),
                "block_reason_counts": dict(sorted(block_counter.items())),
                "block_reason_percentages": percentages(block_counter, len(blocks)),
                "top_block_reasons": reason_counter_to_list(block_counter, len(blocks)),
                "candidate_rejection_reason_counts": dict(sorted(rejection_counter.items())),
                "zero_final_signal_attribution": classify_zero_final_signal_attribution(
                    signal_count=signal_count,
                    block_count=len(blocks),
                    reason_counts=block_counter,
                ),
            }
        )
    return distribution


def reason_counter_for(payloads: list[Mapping[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for payload in payloads:
        counter.update(reason_codes_for(payload))
    return counter


def reason_codes_for(payload: Mapping[str, Any]) -> list[str]:
    codes = [str(code) for code in (payload.get("reason_codes") or []) if str(code)]
    return sorted(codes) if codes else [REASON_BLOCK_REASON_MISSING]


def reason_combination(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(reason_codes_for(payload))


def percentages(counter: Counter[str], denominator: int) -> dict[str, float]:
    if denominator <= 0:
        return {}
    return {key: count / denominator for key, count in sorted(counter.items())}


def reason_counter_to_list(counter: Counter[str], denominator: int, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {
            "reason": key,
            "count": count,
            "percentage": count / denominator if denominator else 0.0,
        }
        for key, count in counter.most_common(limit)
    ]


def classify_zero_final_signal_attribution(
    *,
    signal_count: int,
    block_count: int,
    reason_counts: Counter[str],
) -> dict[str, Any]:
    if signal_count > 0:
        return {
            "classification": "HAS_FINAL_SIGNALS",
            "zero_final_signal_count": False,
            "dominant_reason": None,
            "dominant_reason_share": None,
            "one_dominant_rule": False,
            "dominant_rule_threshold": DOMINANT_RULE_THRESHOLD,
        }
    if block_count <= 0:
        return {
            "classification": "NO_BLOCKS",
            "zero_final_signal_count": True,
            "dominant_reason": None,
            "dominant_reason_share": None,
            "one_dominant_rule": False,
            "dominant_rule_threshold": DOMINANT_RULE_THRESHOLD,
        }
    if not reason_counts:
        return {
            "classification": "UNKNOWN",
            "zero_final_signal_count": True,
            "dominant_reason": None,
            "dominant_reason_share": None,
            "one_dominant_rule": False,
            "dominant_rule_threshold": DOMINANT_RULE_THRESHOLD,
        }
    dominant_reason, dominant_count = reason_counts.most_common(1)[0]
    share = dominant_count / block_count
    one_dominant_rule = share >= DOMINANT_RULE_THRESHOLD
    return {
        "classification": "DOMINANT_RULE" if one_dominant_rule else "DISTRIBUTED_FILTERS",
        "zero_final_signal_count": True,
        "dominant_reason": dominant_reason,
        "dominant_reason_share": share,
        "one_dominant_rule": one_dominant_rule,
        "dominant_rule_threshold": DOMINANT_RULE_THRESHOLD,
    }


def build_campaign_distribution(
    all_payloads: list[Mapping[str, Any]],
    unique_payloads: list[Mapping[str, Any]],
    campaigns: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metadata_by_id = {str(payload.get("campaign_id")): payload for payload in campaigns if payload.get("campaign_id")}
    all_counts: Counter[str] = Counter(campaign_key(payload) for payload in all_payloads)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for payload in unique_payloads:
        grouped[campaign_key(payload)].append(payload)

    campaign_ids = sorted(set(all_counts) | set(grouped) | set(metadata_by_id))
    distribution: list[dict[str, Any]] = []
    for campaign_id in campaign_ids:
        payloads = grouped.get(campaign_id, [])
        metadata = metadata_by_id.get(campaign_id)
        metrics = summarize_live_observations(payloads)
        distribution.append(
            {
                "campaign_id": None if campaign_id == "__no_campaign__" else campaign_id,
                "metadata_present": metadata is not None,
                "started_at_utc": metadata.get("started_at_utc") if metadata else None,
                "ended_at_utc": metadata.get("ended_at_utc") if metadata else None,
                "total_poll_iterations": metadata.get("total_poll_iterations") if metadata else None,
                "duplicate_bar_skipped": int(metadata.get("duplicate_bar_skipped") or 0) if metadata else 0,
                "valid_journal_count": all_counts.get(campaign_id, 0),
                "unique_closed_bars": metrics["unique_closed_bars"],
                "signal_count": metrics["signal_count"],
                "candidate_signal_count": metrics["candidate_signal_count"],
                "block_count": metrics["block_count"],
                "skip_count": metrics["skip_count"],
                "signal_rate": metrics["signal_rate"],
                "candidate_signal_rate": metrics["candidate_signal_rate"],
                "block_rate": metrics["block_rate"],
                "top_block_reasons": metrics["top_block_reasons"],
                "avg_spread": metrics["avg_spread"],
                "max_spread": metrics["max_spread"],
            }
        )
    return distribution


def build_closed_bar_distribution(payloads: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for payload in payloads:
        closed_bar_time = str(payload.get("latest_closed_bar_time") or "UNKNOWN")
        grouped[closed_bar_time].append(payload)

    distribution: list[dict[str, Any]] = []
    for closed_bar_time in sorted(grouped):
        group = grouped[closed_bar_time]
        final_counter = Counter(str(payload.get("final_decision")) for payload in group)
        reason_counter: Counter[str] = Counter()
        campaign_ids = sorted({str(payload.get("campaign_id")) for payload in group if payload.get("campaign_id")})
        for payload in group:
            reason_counter.update(str(code) for code in (payload.get("reason_codes") or []))
        distribution.append(
            {
                "latest_closed_bar_time": closed_bar_time,
                "observation_count": len(group),
                "campaign_ids": campaign_ids,
                "signal_count": final_counter.get("SIGNAL", 0),
                "candidate_signal_count": sum(1 for payload in group if is_candidate_signal(payload)),
                "block_count": final_counter.get("BLOCK", 0),
                "skip_count": final_counter.get("SKIP", 0),
                "final_decision_counts": dict(sorted(final_counter.items())),
                "reason_code_counts": dict(sorted(reason_counter.items())),
            }
        )
    return distribution


def scan_safety_boundaries(
    journals: list[Mapping[str, Any]],
    campaigns: list[Mapping[str, Any]],
) -> dict[str, int]:
    journal_orders_sent = sum(int(payload.get("orders_sent") or 0) for payload in journals)
    campaign_orders_sent = sum(
        int(payload.get("orders_sent") or 0) + int(payload.get("observed_orders_sent_sum") or 0)
        for payload in campaigns
    )
    return {
        "observed_orders_sent_sum": journal_orders_sent + campaign_orders_sent,
        "order_check_called_count": sum(1 for payload in journals if bool(payload.get("order_check_called"))),
        "order_send_called_count": sum(1 for payload in journals if bool(payload.get("order_send_called"))),
    }


def build_historical_comparison(
    *,
    historical_args: argparse.Namespace | None,
    live_payloads: list[Mapping[str, Any]],
    min_live_bars: int,
    build_historical_if_missing: bool,
) -> dict[str, Any]:
    if historical_args is None:
        return {
            "available": False,
            "reason_codes": [REASON_HISTORICAL_COMPARISON_UNAVAILABLE],
            "reason": "historical comparison args were not provided",
        }

    report_path = Path(historical_args.historical_report)
    if not report_path.exists() and not build_historical_if_missing:
        return {
            "available": False,
            "reason_codes": [REASON_HISTORICAL_COMPARISON_UNAVAILABLE],
            "reason": f"historical replay report not found: {report_path}",
        }

    try:
        historical_report = load_or_build_historical_report(historical_args)
        comparison = compare_live_vs_historical(
            historical_report=historical_report,
            live_payloads=live_payloads,
            min_live_bars=min_live_bars,
            tolerance_z=float(historical_args.tolerance_z),
            live_source_path=Path(historical_args.journal_dir),
        )
    except Exception as exc:
        return {
            "available": False,
            "reason_codes": [REASON_HISTORICAL_COMPARISON_UNAVAILABLE],
            "reason": str(exc),
        }

    return {
        "available": True,
        "source": str(report_path) if report_path.exists() else "built_from_existing_historical_replay_logic",
        "expectation_result": comparison["expectation_result"],
        "reason_codes": comparison["reason_codes"],
        "reasons": comparison["reasons"],
        "historical_actionable_signal_rate": comparison["historical_actionable_signal_rate"],
        "live_actionable_signal_rate": comparison["live_actionable_signal_rate"],
        "historical_average_bars_between_signals": comparison["historical_average_bars_between_signals"],
        "live_bars_observed": comparison["live_bars_observed"],
        "expected_live_signals": comparison["expected_live_signals"],
        "actual_live_signals": comparison["actual_live_signals"],
        "zero_signal_probability": comparison["zero_signal_probability"],
        "historical_summary": comparison["historical_summary"],
        "live_summary": comparison["live_summary"],
    }


def campaign_key(payload: Mapping[str, Any]) -> str:
    return str(payload.get("campaign_id") or "__no_campaign__")


def is_candidate_signal(payload: Mapping[str, Any]) -> bool:
    signal = payload.get("signal")
    return isinstance(signal, Mapping) and signal.get("side") in {"BUY", "SELL"}


def signal_side(payload: Mapping[str, Any]) -> str | None:
    signal = payload.get("signal")
    if isinstance(signal, Mapping):
        side = signal.get("side")
        return str(side) if side is not None else None
    return None


def counter_to_top_list(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [{"reason": key, "count": count} for key, count in counter.most_common(limit)]


def add_reason(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    if code not in codes:
        codes.append(code)
    reasons.append(f"{code}: {reason}")


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader live sample quality analysis")
    print(f"final_decision: {report['final_decision']}")
    print(f"valid journals: {report['total_valid_journals']}")
    print(f"unique closed bars: {report['unique_closed_bars']}")
    print(f"signals: {report['signal_count']}")
    print(f"candidate signals: {report['candidate_signal_count']}")
    print(f"blocks: {report['block_count']}")
    print(f"signal rate: {report['signal_rate']:.4f}")
    print(f"zero-signal sample: {report['zero_signal_across_live_samples']}")
    print(f"historical comparison: {report['historical_comparison'].get('expectation_result')}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze live dry-run sample quality without changing strategy behavior.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--campaign-dir", default=str(DEFAULT_CAMPAIGN_DIR))
    parser.add_argument("--historical-report", default=str(DEFAULT_HISTORICAL_REPORT))
    parser.add_argument("--min-live-bars", type=int, default=100)
    parser.add_argument("--tolerance-z", type=float, default=3.0)
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--input", default="data/gold_m15.csv")
    parser.add_argument("--bars", type=int, default=5_000)
    parser.add_argument("--parameter-report", default=str(DEFAULT_PARAMETER_REPORT))
    parser.add_argument("--fallback-fast-sma", type=int, default=10)
    parser.add_argument("--fallback-slow-sma", type=int, default=40)
    parser.add_argument("--atr-period", type=int, default=14)
    parser.add_argument("--fallback-atr-stop-multiplier", type=float, default=1.5)
    parser.add_argument("--fallback-reward-risk-ratio", type=float, default=1.5)
    parser.add_argument("--terminal-path", default=os.getenv("XM_MT5_TERMINAL_PATH"))
    parser.add_argument("--login", type=int, default=_optional_int(os.getenv("XM_MT5_LOGIN")))
    parser.add_argument("--password", default=os.getenv("XM_MT5_PASSWORD"))
    parser.add_argument("--server", default=os.getenv("XM_MT5_SERVER"))
    parser.add_argument("--timeout-ms", type=int, default=60_000)
    parser.add_argument("--no-build-historical", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
