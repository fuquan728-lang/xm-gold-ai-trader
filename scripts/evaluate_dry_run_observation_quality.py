from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dry_run_campaign_report import (
    DEFAULT_CAMPAIGN_DIR,
    load_campaign_metadata,
    session_name,
)
from scripts.dry_run_signal_report import (
    REASON_JOURNAL_REQUIRED_FIELD_MISSING,
    closed_bar_identity,
    load_dry_run_journals,
    missing_required_fields,
    numeric_or_none,
)
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, PROJECT, REASON_SKIP_DUPLICATE_BAR
from src.broker.execution_safety import REASON_EMERGENCY_STOP_FILE_PRESENT
from src.broker.order_executor import TradingConfig, load_trading_config
from src.strategy.risk_manager import REASON_LOT_BELOW_VOLUME_MIN, REASON_MAX_SPREAD_EXCEEDED


MODE = "dry_run_observation_quality"

REASON_ORDERS_SENT_NONZERO = "ORDERS_SENT_NONZERO"
REASON_ORDER_CHECK_CALLED = "ORDER_CHECK_CALLED"
REASON_ORDER_SEND_CALLED = "ORDER_SEND_CALLED"
REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM = "UNIQUE_CLOSED_BARS_BELOW_MINIMUM"
REASON_OBSERVATIONS_SINGLE_SESSION = "OBSERVATIONS_SINGLE_SESSION"
REASON_MAX_SPREAD_THRESHOLD_EXCEEDED = "MAX_SPREAD_THRESHOLD_EXCEEDED"
REASON_ZERO_ACTIONABLE_SIGNAL_RATE = "ZERO_ACTIONABLE_SIGNAL_RATE"
REASON_TOO_MANY_MALFORMED_JOURNALS = "TOO_MANY_MALFORMED_JOURNALS"


def main() -> int:
    args = parse_args()
    report = evaluate_observation_quality(
        journal_dir=Path(args.journal_dir),
        campaign_dir=Path(args.campaign_dir),
        min_unique_bars=args.min_unique_bars,
        max_spread_points=resolve_max_spread_points(args),
        max_malformed_journals=args.max_malformed_journals,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def evaluate_observation_quality(
    *,
    journal_dir: Path,
    campaign_dir: Path,
    min_unique_bars: int = 100,
    max_spread_points: float = 350.0,
    max_malformed_journals: int = 0,
) -> dict[str, Any]:
    journal_entries = load_dry_run_journals(journal_dir)
    campaign_entries = load_campaign_metadata(campaign_dir)
    valid_journals = [entry["payload"] for entry in journal_entries if entry["payload"] is not None]
    malformed_journal_entries = [entry for entry in journal_entries if entry["payload"] is None]
    valid_campaigns = [entry["payload"] for entry in campaign_entries if entry["payload"] is not None]
    malformed_campaign_entries = [entry for entry in campaign_entries if entry["payload"] is None]
    missing_required_count = sum(1 for payload in valid_journals if missing_required_fields(payload))

    unique_observations = unique_closed_bar_observations(valid_journals)
    reason_counter: Counter[str] = Counter()
    for payload in unique_observations:
        reason_counter.update(payload.get("reason_codes") or [])
    for entry in malformed_journal_entries + malformed_campaign_entries:
        reason_counter.update(entry["reason_codes"])
    if missing_required_count:
        reason_counter.update({REASON_JOURNAL_REQUIRED_FIELD_MISSING: missing_required_count})

    duplicate_bar_skipped = sum(int(payload.get("duplicate_bar_skipped") or payload.get("skip_count") or 0) for payload in valid_campaigns)
    if duplicate_bar_skipped:
        reason_counter.update({REASON_SKIP_DUPLICATE_BAR: duplicate_bar_skipped})

    spreads = [spread for spread in (numeric_or_none(payload.get("current_spread_points")) for payload in unique_observations) if spread is not None]
    session_breakdown = build_session_breakdown(unique_observations)
    buy_signal_count = count_final_signal_side(unique_observations, "BUY")
    sell_signal_count = count_final_signal_side(unique_observations, "SELL")
    candidate_buy_signal_count = count_candidate_signal_side(unique_observations, "BUY")
    candidate_sell_signal_count = count_candidate_signal_side(unique_observations, "SELL")
    actionable_count = buy_signal_count + sell_signal_count
    candidate_signal_count = candidate_buy_signal_count + candidate_sell_signal_count
    total_observations = len(unique_observations)
    actionable_signal_rate = actionable_count / total_observations if total_observations else 0.0
    candidate_signal_rate = candidate_signal_count / total_observations if total_observations else 0.0
    risk_lot_below_min_count = count_code(unique_observations, REASON_LOT_BELOW_VOLUME_MIN)
    spread_too_high_count = count_code(unique_observations, REASON_MAX_SPREAD_EXCEEDED)

    journal_orders_sent = sum(int(payload.get("orders_sent") or 0) for payload in valid_journals)
    campaign_orders_sent = sum(
        int(payload.get("orders_sent") or 0) + int(payload.get("observed_orders_sent_sum") or 0)
        for payload in valid_campaigns
    )
    orders_sent = journal_orders_sent + campaign_orders_sent
    order_check_called_count = sum(1 for payload in valid_journals if bool(payload.get("order_check_called")))
    order_send_called_count = sum(1 for payload in valid_journals if bool(payload.get("order_send_called")))
    total_poll_iterations = sum(
        int(payload.get("total_poll_iterations") or payload.get("total_iterations") or 0)
        for payload in valid_campaigns
    )
    malformed_total = len(malformed_journal_entries) + len(malformed_campaign_entries) + missing_required_count

    gate_codes, gate_reasons = evaluate_quality_gates(
        orders_sent=orders_sent,
        order_check_called_count=order_check_called_count,
        order_send_called_count=order_send_called_count,
        unique_closed_bars=len(unique_observations),
        min_unique_bars=min_unique_bars,
        session_breakdown=session_breakdown,
        max_spread=max(spreads) if spreads else None,
        max_spread_points=max_spread_points,
        actionable_signal_rate=actionable_signal_rate,
        malformed_total=malformed_total,
        max_malformed_journals=max_malformed_journals,
    )
    reason_counter.update(gate_codes)
    final_decision = "PASS"
    if any(code in gate_codes for code in (REASON_ORDERS_SENT_NONZERO, REASON_ORDER_CHECK_CALLED, REASON_ORDER_SEND_CALLED)):
        final_decision = "BLOCK"
    elif gate_codes:
        final_decision = "WARN"

    live_sample_coverage = build_live_sample_coverage(
        journal_dir=journal_dir,
        campaign_dir=campaign_dir,
        unique_closed_bars=len(unique_observations),
        min_unique_bars=min_unique_bars,
        total_observations=total_observations,
        total_poll_iterations=total_poll_iterations,
        duplicate_bar_skipped=duplicate_bar_skipped,
        gate_codes=gate_codes,
    )

    return {
        "project": PROJECT,
        "mode": MODE,
        "journal_dir": str(journal_dir),
        "campaign_dir": str(campaign_dir),
        "total_campaigns": len(valid_campaigns),
        "total_poll_iterations": total_poll_iterations,
        "total_observations": total_observations,
        "unique_closed_bars": len(unique_observations),
        "duplicate_bar_skipped": duplicate_bar_skipped,
        "actionable_signal_rate": actionable_signal_rate,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "avg_spread": sum(spreads) / len(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "session_breakdown": session_breakdown,
        "buy_signal_count": buy_signal_count,
        "sell_signal_count": sell_signal_count,
        "candidate_signal_count": candidate_signal_count,
        "candidate_signal_rate": candidate_signal_rate,
        "candidate_buy_signal_count": candidate_buy_signal_count,
        "candidate_sell_signal_count": candidate_sell_signal_count,
        "risk_lot_below_min_count": risk_lot_below_min_count,
        "spread_too_high_count": spread_too_high_count,
        "orders_sent": orders_sent,
        "order_check_called_count": order_check_called_count,
        "order_send_called_count": order_send_called_count,
        "reason_codes": gate_codes,
        "reasons": gate_reasons,
        "live_sample_coverage": live_sample_coverage,
        "malformed_journals": len(malformed_journal_entries),
        "malformed_campaigns": len(malformed_campaign_entries),
        "missing_required_field_journals": missing_required_count,
        "quality_gates": {
            "min_unique_bars": min_unique_bars,
            "max_spread_points": max_spread_points,
            "max_malformed_journals": max_malformed_journals,
            "reason_codes": gate_codes,
            "reasons": gate_reasons,
        },
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


def build_live_sample_coverage(
    *,
    journal_dir: Path,
    campaign_dir: Path,
    unique_closed_bars: int,
    min_unique_bars: int,
    total_observations: int,
    total_poll_iterations: int,
    duplicate_bar_skipped: int,
    gate_codes: list[str],
) -> dict[str, Any]:
    coverage_codes = [
        code
        for code in gate_codes
        if code in {REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM, REASON_ZERO_ACTIONABLE_SIGNAL_RATE}
    ]
    return {
        "source_name": "dry_run_signal_journals",
        "source_path": str(journal_dir),
        "source_glob": str(journal_dir / "*.json"),
        "campaign_source_name": "dry_run_campaign_metadata",
        "campaign_source_path": str(campaign_dir),
        "current_unique_closed_bars": unique_closed_bars,
        "required_min_unique_closed_bars": min_unique_bars,
        "sufficient_closed_bar_coverage": unique_closed_bars >= min_unique_bars,
        "total_observations": total_observations,
        "total_poll_iterations": total_poll_iterations,
        "duplicate_bar_skipped": duplicate_bar_skipped,
        "warn_reason_codes": coverage_codes,
        "collection_command": (
            "python scripts\\run_dry_observation_campaign.py --symbol GOLD_ --timeframe M15 "
            "--interval-seconds 60 --max-iterations <N> --bar-close-only --json"
        ),
    }


def unique_closed_bar_observations(payloads: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    by_key: dict[tuple[Any, Any, Any, Any], Mapping[str, Any]] = {}
    for payload in payloads:
        key = closed_bar_identity(payload)
        if key is None:
            continue
        previous = by_key.get(key)
        if previous is None or timestamp_value(payload.get("timestamp_utc")) >= timestamp_value(previous.get("timestamp_utc")):
            by_key[key] = payload
    return sorted(by_key.values(), key=lambda payload: str(payload.get("timestamp_utc") or ""))


def evaluate_quality_gates(
    *,
    orders_sent: int,
    order_check_called_count: int,
    order_send_called_count: int,
    unique_closed_bars: int,
    min_unique_bars: int,
    session_breakdown: Mapping[str, Mapping[str, Any]],
    max_spread: float | None,
    max_spread_points: float,
    actionable_signal_rate: float,
    malformed_total: int,
    max_malformed_journals: int,
) -> tuple[list[str], list[str]]:
    codes: list[str] = []
    reasons: list[str] = []
    if orders_sent > 0:
        add_gate(codes, reasons, REASON_ORDERS_SENT_NONZERO, f"orders_sent {orders_sent} > 0")
    if order_check_called_count > 0:
        add_gate(codes, reasons, REASON_ORDER_CHECK_CALLED, f"order_check_called_count {order_check_called_count} > 0")
    if order_send_called_count > 0:
        add_gate(codes, reasons, REASON_ORDER_SEND_CALLED, f"order_send_called_count {order_send_called_count} > 0")
    if unique_closed_bars < min_unique_bars:
        add_gate(
            codes,
            reasons,
            REASON_UNIQUE_CLOSED_BARS_BELOW_MINIMUM,
            f"unique_closed_bars {unique_closed_bars} < min_unique_bars {min_unique_bars}",
        )
    active_sessions = [
        name
        for name, values in session_breakdown.items()
        if int(values.get("observations") or 0) > 0
    ]
    if unique_closed_bars > 0 and len(active_sessions) <= 1:
        add_gate(codes, reasons, REASON_OBSERVATIONS_SINGLE_SESSION, f"active sessions: {active_sessions}")
    if max_spread is not None and max_spread > max_spread_points:
        add_gate(
            codes,
            reasons,
            REASON_MAX_SPREAD_THRESHOLD_EXCEEDED,
            f"max_spread {max_spread:.1f} > threshold {max_spread_points:.1f}",
        )
    if unique_closed_bars >= min_unique_bars and actionable_signal_rate == 0.0:
        add_gate(
            codes,
            reasons,
            REASON_ZERO_ACTIONABLE_SIGNAL_RATE,
            f"actionable_signal_rate is 0 after {unique_closed_bars} unique closed bars",
        )
    if malformed_total > max_malformed_journals:
        add_gate(
            codes,
            reasons,
            REASON_TOO_MANY_MALFORMED_JOURNALS,
            f"malformed or incomplete journals {malformed_total} > {max_malformed_journals}",
        )
    return codes, reasons


def build_session_breakdown(payloads: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    breakdown = {
        "Asia": empty_session(),
        "London": empty_session(),
        "NewYork": empty_session(),
        "OffHours": empty_session(),
    }
    for payload in payloads:
        session = session_name(payload.get("timestamp_utc"))
        signal = payload.get("signal") if isinstance(payload.get("signal"), Mapping) else {}
        side = signal.get("side")
        final_decision = payload.get("final_decision")
        codes = list(payload.get("reason_codes") or [])
        breakdown[session]["observations"] += 1
        breakdown[session]["signals"] += 1 if final_decision == "SIGNAL" else 0
        breakdown[session]["blocks"] += 1 if final_decision == "BLOCK" else 0
        breakdown[session]["buy_signals"] += 1 if final_decision == "SIGNAL" and side == "BUY" else 0
        breakdown[session]["sell_signals"] += 1 if final_decision == "SIGNAL" and side == "SELL" else 0
        breakdown[session]["candidate_buy_signals"] += 1 if side == "BUY" else 0
        breakdown[session]["candidate_sell_signals"] += 1 if side == "SELL" else 0
        breakdown[session]["reason_code_counts"].update(codes)
    return {
        name: {
            "observations": values["observations"],
            "signals": values["signals"],
            "blocks": values["blocks"],
            "buy_signals": values["buy_signals"],
            "sell_signals": values["sell_signals"],
            "candidate_buy_signals": values["candidate_buy_signals"],
            "candidate_sell_signals": values["candidate_sell_signals"],
            "reason_code_counts": dict(sorted(values["reason_code_counts"].items())),
        }
        for name, values in breakdown.items()
    }


def empty_session() -> dict[str, Any]:
    return {
        "observations": 0,
        "signals": 0,
        "blocks": 0,
        "buy_signals": 0,
        "sell_signals": 0,
        "candidate_buy_signals": 0,
        "candidate_sell_signals": 0,
        "reason_code_counts": Counter(),
    }


def count_final_signal_side(payloads: list[Mapping[str, Any]], side: str) -> int:
    return sum(1 for payload in payloads if payload.get("final_decision") == "SIGNAL" and signal_side(payload) == side)


def count_candidate_signal_side(payloads: list[Mapping[str, Any]], side: str) -> int:
    count = 0
    for payload in payloads:
        if signal_side(payload) == side:
            count += 1
    return count


def signal_side(payload: Mapping[str, Any]) -> str | None:
    signal = payload.get("signal")
    if isinstance(signal, Mapping):
        side = signal.get("side")
        return str(side) if side is not None else None
    return None


def count_code(payloads: list[Mapping[str, Any]], code: str) -> int:
    count = 0
    for payload in payloads:
        codes = list(payload.get("reason_codes") or [])
        risk_codes = list((payload.get("risk_preview") or {}).get("reason_codes") or [])
        if code in codes or code in risk_codes:
            count += 1
    return count


def add_gate(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    codes.append(code)
    reasons.append(f"{code}: {reason}")


def timestamp_value(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def resolve_max_spread_points(args: argparse.Namespace) -> float:
    return float(args.max_spread_points)


def load_or_default_config(path: str) -> TradingConfig:
    config_path = Path(path)
    if config_path.exists():
        return load_trading_config(config_path)
    return TradingConfig()


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader dry-run observation quality")
    print(f"final_decision: {report['final_decision']}")
    print(f"campaigns: {report['total_campaigns']}")
    print(f"poll iterations: {report['total_poll_iterations']}")
    print(f"unique closed bars: {report['unique_closed_bars']}")
    print(f"actionable signal rate: {report['actionable_signal_rate']:.4f}")
    print(f"avg spread: {report['avg_spread']}")
    print(f"max spread: {report['max_spread']}")
    print(f"orders_sent: {report['orders_sent']}")
    if report["quality_gates"]["reason_codes"]:
        print(f"quality gates: {', '.join(report['quality_gates']['reason_codes'])}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate dry-run observation quality gates.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--campaign-dir", default=str(DEFAULT_CAMPAIGN_DIR))
    parser.add_argument("--min-unique-bars", type=int, default=100)
    parser.add_argument("--max-spread-points", type=float, default=350.0)
    parser.add_argument("--max-malformed-journals", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
