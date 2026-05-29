from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backtest_baseline_report import load_backtest_inputs
from scripts.dry_run_signal_report import load_dry_run_journals
from scripts.evaluate_dry_run_observation_quality import unique_closed_bar_observations
from scripts.historical_signal_replay import run_historical_signal_replay
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, DEFAULT_PARAMETER_REPORT, PROJECT, selected_signal_config
from src.broker.mt5_client import MT5ClientError
from src.logging_config import configure_logging


MODE = "compare_live_vs_historical_signal_rate"
DEFAULT_HISTORICAL_REPORT = Path("reports/backtests/historical_signal_replay_report.json")

REASON_LOW_LIVE_SIGNAL_RATE = "LOW_LIVE_SIGNAL_RATE"
REASON_HIGH_LIVE_SIGNAL_RATE = "HIGH_LIVE_SIGNAL_RATE"
REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION = "LIVE_SIGNAL_RATE_WITHIN_EXPECTATION"
REASON_INSUFFICIENT_LIVE_SAMPLE = "INSUFFICIENT_LIVE_SAMPLE"
REASON_HISTORICAL_RATE_UNAVAILABLE = "HISTORICAL_RATE_UNAVAILABLE"


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="compare_live_vs_historical_signal_rate")
    try:
        historical_report = load_or_build_historical_report(args)
    except (MT5ClientError, RuntimeError, ValueError) as exc:
        logger.error("%s", exc)
        print(str(exc), file=sys.stderr)
        return 1

    live_entries = load_dry_run_journals(Path(args.live_journal_dir))
    live_payloads = [entry["payload"] for entry in live_entries if entry["payload"] is not None]
    report = compare_live_vs_historical(
        historical_report=historical_report,
        live_payloads=live_payloads,
        min_live_bars=args.min_live_bars,
        tolerance_z=args.tolerance_z,
        live_source_path=Path(args.live_journal_dir),
    )
    report["live_summary"]["malformed_journals"] = len([entry for entry in live_entries if entry["payload"] is None])
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def load_or_build_historical_report(args: argparse.Namespace) -> dict[str, Any]:
    report_path = Path(args.historical_report)
    if report_path.exists():
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("historical replay report must be a JSON object")
        return payload

    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to build historical replay fallback. Install requirements.txt.") from exc

    bars, symbol_info, data_source = load_backtest_inputs(args, pd)
    if args.bars and len(bars) > args.bars:
        bars = bars.tail(args.bars).reset_index(drop=True)
        data_source = {**data_source, "bars_replayed_from_tail": int(args.bars)}
    signal_config, parameter_source = selected_signal_config(args)
    return run_historical_signal_replay(
        bars=bars,
        symbol=args.symbol,
        timeframe=args.timeframe,
        symbol_info=symbol_info,
        signal_config=signal_config,
        selected_parameters_source=parameter_source,
        data_source=data_source,
    )


def compare_live_vs_historical(
    *,
    historical_report: Mapping[str, Any],
    live_payloads: list[Mapping[str, Any]],
    min_live_bars: int = 100,
    tolerance_z: float = 3.0,
    live_source_path: Path | None = None,
) -> dict[str, Any]:
    historical = historical_summary(historical_report)
    live = live_summary(live_payloads)
    expectation = evaluate_expectation(
        historical_actionable_signal_rate=historical["historical_actionable_signal_rate"],
        live_bars_observed=live["live_bars_observed"],
        actual_live_signals=live["actual_live_signals"],
        min_live_bars=min_live_bars,
        tolerance_z=tolerance_z,
    )
    return {
        "project": PROJECT,
        "mode": MODE,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orders_sent": 0,
        "order_check_called": False,
        "order_send_called": False,
        "historical_actionable_signal_rate": historical["historical_actionable_signal_rate"],
        "live_actionable_signal_rate": live["live_actionable_signal_rate"],
        "historical_average_bars_between_signals": historical["historical_average_bars_between_signals"],
        "live_bars_observed": live["live_bars_observed"],
        "expected_live_signals": expectation["expected_live_signals"],
        "actual_live_signals": live["actual_live_signals"],
        "zero_signal_probability": expectation["zero_signal_probability"],
        "historical_summary": historical,
        "live_summary": live,
        "live_sample_coverage": build_live_sample_coverage(
            live=live,
            min_live_bars=min_live_bars,
            reason_codes=expectation["reason_codes"],
            live_source_path=live_source_path,
        ),
        "expectation_result": expectation["expectation_result"],
        "reason_codes": expectation["reason_codes"],
        "reasons": expectation["reasons"],
        "expectation": expectation,
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
}


def build_live_sample_coverage(
    *,
    live: Mapping[str, Any],
    min_live_bars: int,
    reason_codes: list[str],
    live_source_path: Path | None,
) -> dict[str, Any]:
    observed = int(live.get("live_bars_observed") or 0)
    source_path = live_source_path or Path("logs/dry_run_signals")
    return {
        "source_name": "dry_run_signal_journals",
        "source_path": str(source_path),
        "source_glob": str(source_path / "*.json"),
        "current_unique_closed_bars": observed,
        "required_min_unique_closed_bars": min_live_bars,
        "sufficient_closed_bar_coverage": observed >= min_live_bars,
        "warn_reason_codes": [
            code
            for code in reason_codes
            if code in {REASON_INSUFFICIENT_LIVE_SAMPLE, REASON_LOW_LIVE_SIGNAL_RATE, REASON_HIGH_LIVE_SIGNAL_RATE}
        ],
    }


def historical_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    rate = float(report.get("actionable_signal_rate") or 0.0)
    diagnostics = report.get("diagnostics") if isinstance(report.get("diagnostics"), Mapping) else {}
    return {
        "historical_actionable_signal_rate": rate,
        "historical_average_bars_between_signals": diagnostics.get("average_bars_between_signals"),
        "historical_total_observations": int(report.get("total_observations") or report.get("total_bars_replayed") or 0),
        "historical_signal_count": int(report.get("signal_count") or 0),
        "historical_buy_signal_count": int(report.get("buy_signal_count") or report.get("BUY_count") or 0),
        "historical_sell_signal_count": int(report.get("sell_signal_count") or report.get("SELL_count") or 0),
        "source": report.get("data_source", {}),
    }


def live_summary(payloads: list[Mapping[str, Any]]) -> dict[str, Any]:
    unique = unique_closed_bar_observations(payloads)
    actual_signals = [payload for payload in unique if is_actionable_live_signal(payload)]
    buy_count = sum(1 for payload in actual_signals if signal_side(payload) == "BUY")
    sell_count = sum(1 for payload in actual_signals if signal_side(payload) == "SELL")
    observed_order_check_calls = sum(1 for payload in payloads if bool(payload.get("order_check_called")))
    observed_order_send_calls = sum(1 for payload in payloads if bool(payload.get("order_send_called")))
    observed_orders_sent_sum = sum(int(payload.get("orders_sent") or 0) for payload in payloads)
    live_bars = len(unique)
    return {
        "live_bars_observed": live_bars,
        "actual_live_signals": len(actual_signals),
        "live_actionable_signal_rate": len(actual_signals) / live_bars if live_bars else 0.0,
        "live_buy_signal_count": buy_count,
        "live_sell_signal_count": sell_count,
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "observed_order_check_called_count": observed_order_check_calls,
        "observed_order_send_called_count": observed_order_send_calls,
    }


def evaluate_expectation(
    *,
    historical_actionable_signal_rate: float,
    live_bars_observed: int,
    actual_live_signals: int,
    min_live_bars: int,
    tolerance_z: float,
) -> dict[str, Any]:
    p = max(0.0, min(1.0, historical_actionable_signal_rate))
    expected = live_bars_observed * p
    variance = live_bars_observed * p * (1.0 - p)
    stddev = math.sqrt(variance)
    lower = max(0.0, expected - (tolerance_z * stddev))
    upper = expected + (tolerance_z * stddev)
    zero_probability = (1.0 - p) ** live_bars_observed if live_bars_observed >= 0 else None

    if p <= 0:
        return expectation_payload(
            result="NORMAL",
            code=REASON_HISTORICAL_RATE_UNAVAILABLE,
            reason="historical actionable signal rate is zero or unavailable",
            expected=expected,
            lower=lower,
            upper=upper,
            zero_probability=zero_probability,
            min_live_bars=min_live_bars,
        )

    if live_bars_observed < min_live_bars:
        return expectation_payload(
            result="NORMAL",
            code=REASON_INSUFFICIENT_LIVE_SAMPLE,
            reason=f"live unique bars {live_bars_observed} < minimum sample {min_live_bars}",
            expected=expected,
            lower=lower,
            upper=upper,
            zero_probability=zero_probability,
            min_live_bars=min_live_bars,
        )

    if actual_live_signals < lower:
        return expectation_payload(
            result="LOW_SIGNAL_WARNING",
            code=REASON_LOW_LIVE_SIGNAL_RATE,
            reason=f"actual live signals {actual_live_signals} below lower tolerance {lower:.2f}",
            expected=expected,
            lower=lower,
            upper=upper,
            zero_probability=zero_probability,
            min_live_bars=min_live_bars,
        )

    if actual_live_signals > upper:
        return expectation_payload(
            result="HIGH_SIGNAL_WARNING",
            code=REASON_HIGH_LIVE_SIGNAL_RATE,
            reason=f"actual live signals {actual_live_signals} above upper tolerance {upper:.2f}",
            expected=expected,
            lower=lower,
            upper=upper,
            zero_probability=zero_probability,
            min_live_bars=min_live_bars,
        )

    return expectation_payload(
        result="NORMAL",
        code=REASON_LIVE_SIGNAL_RATE_WITHIN_EXPECTATION,
        reason="live signal rate is within historical expectation tolerance",
        expected=expected,
        lower=lower,
        upper=upper,
        zero_probability=zero_probability,
        min_live_bars=min_live_bars,
    )


def expectation_payload(
    *,
    result: str,
    code: str,
    reason: str,
    expected: float,
    lower: float,
    upper: float,
    zero_probability: float | None,
    min_live_bars: int,
) -> dict[str, Any]:
    return {
        "expectation_result": result,
        "reason_codes": [code],
        "reasons": [f"{code}: {reason}"],
        "expected_live_signals": expected,
        "tolerance_band": {"lower": lower, "upper": upper},
        "zero_signal_probability": zero_probability,
        "min_live_bars": min_live_bars,
    }


def is_actionable_live_signal(payload: Mapping[str, Any]) -> bool:
    return payload.get("final_decision") == "SIGNAL" or signal_side(payload) in {"BUY", "SELL"}


def signal_side(payload: Mapping[str, Any]) -> str | None:
    signal = payload.get("signal")
    if isinstance(signal, Mapping):
        side = signal.get("side")
        return str(side) if side is not None else None
    return None


def print_summary(report: Mapping[str, Any]) -> None:
    historical = report["historical_summary"]
    live = report["live_summary"]
    print("xm-gold-ai-trader live vs historical signal expectation")
    print(f"expectation_result: {report['expectation_result']}")
    print(f"historical rate: {historical['historical_actionable_signal_rate']:.4f}")
    print(f"live rate: {live['live_actionable_signal_rate']:.4f}")
    print(f"live bars: {live['live_bars_observed']}")
    print(f"actual live signals: {live['actual_live_signals']}")
    print(f"expected live signals: {report['expectation']['expected_live_signals']:.2f}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare live dry-run signal rate against historical replay expectation.")
    parser.add_argument("--historical-report", default=str(DEFAULT_HISTORICAL_REPORT))
    parser.add_argument("--live-journal-dir", default=str(DEFAULT_JOURNAL_DIR))
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
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _optional_int(value: str | None) -> int | None:
    return int(value) if value else None


if __name__ == "__main__":
    raise SystemExit(main())
