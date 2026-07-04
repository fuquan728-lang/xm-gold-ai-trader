from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.observation_journal import DEFAULT_JOURNAL_DIR, iter_observations, normalize_action, safe_float


MODE = "spread_regime_report"
CAMPAIGN_VERSION = "v0.26.0"

DEFAULT_TARGET = 300
DEFAULT_SPREAD_THRESHOLD = 3.0
DEFAULT_P75_THRESHOLD = 3.5
DEFAULT_UNSUITABLE_P50 = 4.5

SESSION_WINDOWS = (
    ("new_york", tuple(list(range(0, 5)) + list(range(21, 24)))),
    ("asia", tuple(range(6, 15))),
    ("london", tuple(range(15, 21))),
    ("transition", (5,)),
)


def main() -> int:
    args = parse_args()
    observations, source = load_report_observations(args)
    timeframe = args.timeframe or source.get("timeframe") or "M5"
    report = build_spread_regime_report(
        observations,
        symbol=args.symbol,
        timeframe=timeframe,
        target=args.target,
        spread_threshold=args.spread_threshold,
        p75_threshold=args.p75_threshold,
        unsuitable_p50=args.unsuitable_p50,
        data_source=source,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0


def build_spread_regime_report(
    observations: Iterable[Mapping[str, Any]],
    *,
    symbol: str = "GOLD_",
    timeframe: str = "M5",
    target: int = DEFAULT_TARGET,
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
    p75_threshold: float = DEFAULT_P75_THRESHOLD,
    unsuitable_p50: float = DEFAULT_UNSUITABLE_P50,
    data_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = []
    malformed = 0
    missing_required = 0
    for row in observations:
        payload = dict(row)
        if payload.get("_malformed"):
            malformed += 1
            continue
        if payload.get("symbol") != symbol or payload.get("timeframe") != timeframe:
            continue
        spread = safe_float(payload.get("spread_pips"))
        timestamp = parse_timestamp(payload.get("timestamp"))
        if spread is None or timestamp is None:
            missing_required += 1
            continue
        payload["_spread_pips"] = spread
        payload["_timestamp"] = timestamp
        payload["_session"] = classify_session(timestamp.hour)
        rows.append(payload)

    total = len(rows)
    matched = sum(1 for row in rows if row.get("response_matched") is True)
    stale = sum(1 for row in rows if row.get("stale_response") is True)
    timeouts = sum(1 for row in rows if row.get("timeout") is True)
    trades = sum(1 for row in rows if row.get("trade_executed") is True)
    journal_quality_pass = (
        total > 0
        and matched == total
        and stale == 0
        and timeouts == 0
        and trades == 0
        and malformed == 0
        and missing_required == 0
    )

    raw_counter = Counter(normalize_action(row.get("ai_action_raw")) for row in rows)
    final_counter = Counter(normalize_action(row.get("ai_action_final")) for row in rows)
    block_counter: Counter[str] = Counter()
    for row in rows:
        block_counter.update(str(item) for item in (row.get("blocked_by") or []))

    spread_values = [row["_spread_pips"] for row in rows]
    spread_summary = numeric_summary(spread_values, spread_threshold)
    session_rows = []
    for session_name, _hours in SESSION_WINDOWS:
        scoped = [row for row in rows if row["_session"] == session_name]
        session_rows.append(build_session_summary(session_name, scoped, spread_threshold, p75_threshold))
    hour_rows = [
        build_hour_summary(hour, [row for row in rows if row["_timestamp"].hour == hour], spread_threshold, p75_threshold)
        for hour in range(24)
    ]

    status, reason = decide_status(
        total=total,
        target=target,
        journal_quality_pass=journal_quality_pass,
        spread_summary=spread_summary,
        session_rows=session_rows,
        hour_rows=hour_rows,
        spread_threshold=spread_threshold,
        p75_threshold=p75_threshold,
        unsuitable_p50=unsuitable_p50,
    )

    return {
        "project": "xm-gold-ai-trader",
        "mode": MODE,
        "campaign_version": CAMPAIGN_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_source": dict(data_source or {"kind": "observation_journal"}),
        "target": target,
        "status": status,
        "reason": reason,
        "session_timezone": "Asia/Shanghai local service time",
        "session_windows": {
            "asia": "06:00-14:59",
            "london": "15:00-20:59",
            "new_york": "21:00-04:59",
            "transition": "05:00-05:59",
        },
        "total_observations": total,
        "target_met": total >= target,
        "journal_quality_pass": journal_quality_pass,
        "matched_responses": matched,
        "stale_responses_ignored": stale,
        "timeouts": timeouts,
        "trades_executed": trades,
        "malformed_journals": malformed,
        "missing_required_field_journals": missing_required,
        "raw_action_counts": action_counts(raw_counter),
        "final_action_counts": action_counts(final_counter),
        "raw_buy_to_hold": sum(
            1
            for row in rows
            if normalize_action(row.get("ai_action_raw")) == "BUY"
            and normalize_action(row.get("ai_action_final")) == "HOLD"
        ),
        "raw_sell_to_hold": sum(
            1
            for row in rows
            if normalize_action(row.get("ai_action_raw")) == "SELL"
            and normalize_action(row.get("ai_action_final")) == "HOLD"
        ),
        "blocked_by_counts": dict(sorted(block_counter.items())),
        "blocked_by_percentages": percentages(block_counter, total),
        "spread_threshold_pips": spread_threshold,
        "candidate_p75_threshold_pips": p75_threshold,
        "unsuitable_p50_threshold_pips": unsuitable_p50,
        "spread_pips": spread_summary,
        "latency_ms": numeric_summary([safe_float(row.get("latency_ms")) for row in rows], None),
        "confidence": numeric_summary([safe_float(row.get("confidence")) for row in rows], None),
        "spread_buckets": spread_buckets(spread_values),
        "sessions": session_rows,
        "hours": hour_rows,
        "best_hours_by_p75": best_windows(hour_rows, "hour", limit=5),
    }


def load_report_observations(args: argparse.Namespace) -> tuple[Iterable[Mapping[str, Any]], dict[str, Any]]:
    if args.historical_csv:
        metadata = load_symbol_metadata(Path(args.symbol_info)) if args.symbol_info else None
        timeframe = args.timeframe or (metadata or {}).get("timeframe") or "M15"
        rows = list(
            iter_historical_spread_observations(
                Path(args.historical_csv),
                symbol=args.symbol,
                timeframe=timeframe,
                symbol_info=(metadata or {}).get("symbol_info"),
                spread_threshold=args.spread_threshold,
            )
        )
        return rows, {
            "kind": "historical_csv",
            "path": str(args.historical_csv),
            "symbol_info": str(args.symbol_info) if args.symbol_info else None,
            "timeframe": timeframe,
        }
    timeframe = args.timeframe or "M5"
    return iter_observations(args.journal_dir), {
        "kind": "observation_journal",
        "path": str(args.journal_dir),
        "timeframe": timeframe,
    }


def iter_historical_spread_observations(
    csv_path: Path,
    *,
    symbol: str,
    timeframe: str,
    symbol_info: Mapping[str, Any] | None = None,
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
) -> Iterable[dict[str, Any]]:
    point = safe_float((symbol_info or {}).get("point")) or default_point(symbol)
    pip_size = default_pip_size(symbol)
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            timestamp = parse_historical_timestamp(row.get("time"))
            spread_points = safe_float(row.get("spread"))
            if timestamp is None or spread_points is None:
                continue
            spread_pips = spread_points * point / pip_size if pip_size > 0 else None
            if spread_pips is None:
                continue
            blocked_by = ["ACTION_HOLD"]
            if spread_pips > spread_threshold:
                blocked_by.append("SPREAD_TOO_HIGH")
            yield {
                "timestamp": timestamp.isoformat(),
                "request_id": f"HIST_{symbol}_{timeframe}_{index}",
                "symbol": symbol,
                "timeframe": timeframe,
                "bid": safe_float(row.get("close")),
                "ask": (safe_float(row.get("close")) or 0.0) + (spread_points * point),
                "spread_pips": spread_pips,
                "ai_action_raw": "HOLD",
                "ai_action_final": "HOLD",
                "confidence": None,
                "blocked_by": blocked_by,
                "response_matched": True,
                "stale_response": False,
                "timeout": False,
                "trade_executed": False,
                "latency_ms": 0,
                "source_bar_time": row.get("time"),
                "tick_volume": safe_float(row.get("tick_volume")),
            }


def load_symbol_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def parse_historical_timestamp(value: Any) -> datetime | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(local_timezone())


def local_timezone() -> timezone:
    return timezone(timedelta(hours=8), name="Asia/Shanghai")


def default_point(symbol: str) -> float:
    if "GOLD" in symbol.upper() or symbol.upper().startswith("XAU"):
        return 0.01
    return 0.00001


def default_pip_size(symbol: str) -> float:
    if "GOLD" in symbol.upper() or symbol.upper().startswith("XAU"):
        return 0.10
    return 0.0001


def decide_status(
    *,
    total: int,
    target: int,
    journal_quality_pass: bool,
    spread_summary: Mapping[str, Any],
    session_rows: list[Mapping[str, Any]],
    hour_rows: list[Mapping[str, Any]],
    spread_threshold: float,
    p75_threshold: float,
    unsuitable_p50: float,
) -> tuple[str, str]:
    if total < target:
        return (
            "IN_PROGRESS",
            f"total_observations={total} < target={target}; keep collecting spread evidence",
        )
    if not journal_quality_pass:
        return ("FAIL", "journal quality gate failed; do not evaluate spread readiness")

    p50 = spread_summary.get("p50")
    p75 = spread_summary.get("p75")
    if p50 is not None and p75 is not None and p50 <= spread_threshold and p75 <= p75_threshold:
        return (
            "PASS",
            f"overall spread regime tradable: p50={p50:.2f} <= {spread_threshold:.2f}, p75={p75:.2f} <= {p75_threshold:.2f}",
        )

    tradable_sessions = [
        row["session"]
        for row in session_rows
        if row.get("observation_count", 0) > 0
        and row.get("p50") is not None
        and row.get("p75") is not None
        and row["p50"] <= spread_threshold
        and row["p75"] <= p75_threshold
    ]
    if tradable_sessions:
        return (
            "SESSION_GATE_CANDIDATE",
            "only selected sessions meet the spread gate: " + ", ".join(tradable_sessions),
        )

    tradable_hours = [
        str(row["hour"])
        for row in hour_rows
        if row.get("observation_count", 0) > 0
        and row.get("p50") is not None
        and row.get("p75") is not None
        and row["p50"] <= spread_threshold
        and row["p75"] <= p75_threshold
    ]
    if tradable_hours:
        return (
            "HOUR_GATE_CANDIDATE",
            "only selected local hours meet the spread gate: " + ", ".join(tradable_hours),
        )

    if p50 is not None and p50 > unsuitable_p50:
        return (
            "BLOCKED",
            f"spread regime not tradable for current M5 system: p50={p50:.2f} > {unsuitable_p50:.2f}",
        )

    return (
        "BLOCKED",
        f"no session meets spread gate p50<={spread_threshold:.2f} and p75<={p75_threshold:.2f}",
    )


def build_session_summary(
    session_name: str,
    rows: list[Mapping[str, Any]],
    spread_threshold: float,
    p75_threshold: float,
) -> dict[str, Any]:
    spreads = [row["_spread_pips"] for row in rows]
    summary = numeric_summary(spreads, spread_threshold)
    raw_counter = Counter(normalize_action(row.get("ai_action_raw")) for row in rows)
    final_counter = Counter(normalize_action(row.get("ai_action_final")) for row in rows)
    summary.update(
        {
            "session": session_name,
            "observation_count": len(rows),
            "raw_action_counts": action_counts(raw_counter),
            "final_action_counts": action_counts(final_counter),
            "tradable_candidate": (
                bool(rows)
                and summary.get("p50") is not None
                and summary.get("p75") is not None
                and summary["p50"] <= spread_threshold
                and summary["p75"] <= p75_threshold
            ),
        }
    )
    return summary


def build_hour_summary(
    hour: int,
    rows: list[Mapping[str, Any]],
    spread_threshold: float,
    p75_threshold: float,
) -> dict[str, Any]:
    spreads = [row["_spread_pips"] for row in rows]
    summary = numeric_summary(spreads, spread_threshold)
    raw_counter = Counter(normalize_action(row.get("ai_action_raw")) for row in rows)
    final_counter = Counter(normalize_action(row.get("ai_action_final")) for row in rows)
    summary.update(
        {
            "hour": hour,
            "session": classify_session(hour),
            "observation_count": len(rows),
            "raw_action_counts": action_counts(raw_counter),
            "final_action_counts": action_counts(final_counter),
            "tradable_candidate": (
                bool(rows)
                and summary.get("p50") is not None
                and summary.get("p75") is not None
                and summary["p50"] <= spread_threshold
                and summary["p75"] <= p75_threshold
            ),
        }
    )
    return summary


def best_windows(rows: list[Mapping[str, Any]], key: str, *, limit: int) -> list[dict[str, Any]]:
    populated = [row for row in rows if row.get("observation_count", 0) > 0 and row.get("p75") is not None]
    ranked = sorted(populated, key=lambda row: (row.get("p75"), row.get("p50"), -row.get("observation_count", 0)))
    return [
        {
            key: row[key],
            "session": row.get("session"),
            "observation_count": row.get("observation_count"),
            "p50": row.get("p50"),
            "p75": row.get("p75"),
            "at_or_below_threshold_pct": row.get("at_or_below_threshold_pct"),
            "tradable_candidate": row.get("tradable_candidate"),
        }
        for row in ranked[:limit]
    ]


def classify_session(hour: int) -> str:
    for session_name, hours in SESSION_WINDOWS:
        if hour in hours:
            return session_name
    return "unknown"


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def numeric_summary(values: Iterable[float | None], threshold: float | None) -> dict[str, Any]:
    clean = sorted(float(value) for value in values if value is not None and not math.isnan(float(value)))
    if not clean:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "p50": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "max": None,
            "avg": None,
            "at_or_below_threshold_count": 0 if threshold is not None else None,
            "at_or_below_threshold_pct": 0.0 if threshold is not None else None,
        }
    result = {
        "count": len(clean),
        "min": round(clean[0], 4),
        "p25": round(quantile(clean, 0.25), 4),
        "p50": round(quantile(clean, 0.50), 4),
        "p75": round(quantile(clean, 0.75), 4),
        "p90": round(quantile(clean, 0.90), 4),
        "p95": round(quantile(clean, 0.95), 4),
        "max": round(clean[-1], 4),
        "avg": round(sum(clean) / len(clean), 4),
    }
    if threshold is not None:
        count = sum(1 for value in clean if value <= threshold)
        result["at_or_below_threshold_count"] = count
        result["at_or_below_threshold_pct"] = round(count / len(clean), 4)
    return result


def quantile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * pct
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def action_counts(counter: Counter[str]) -> dict[str, int]:
    return {"BUY": counter["BUY"], "SELL": counter["SELL"], "HOLD": counter["HOLD"]}


def percentages(counter: Counter[str], total: int) -> dict[str, float]:
    if total <= 0:
        return {key: 0.0 for key in sorted(counter)}
    return {key: round(value / total, 4) for key, value in sorted(counter.items())}


def spread_buckets(values: Iterable[float]) -> dict[str, int]:
    clean = [float(value) for value in values]
    return {
        "<=3.0": sum(1 for value in clean if value <= 3.0),
        "3.0-4.0": sum(1 for value in clean if 3.0 < value <= 4.0),
        "4.0-5.0": sum(1 for value in clean if 4.0 < value <= 5.0),
        "5.0-6.0": sum(1 for value in clean if 5.0 < value <= 6.0),
        ">6.0": sum(1 for value in clean if value > 6.0),
    }


def print_summary(report: Mapping[str, Any]) -> None:
    spread = report["spread_pips"]
    print("xm-gold-ai-trader spread regime report")
    print(f"campaign: {report['campaign_version']}")
    print(f"symbol/timeframe: {report['symbol']} {report['timeframe']}")
    print(f"status: {report['status']}")
    print(f"reason: {report['reason']}")
    print(f"total_observations: {report['total_observations']} / {report['target']}")
    print(f"journal_quality_pass: {report['journal_quality_pass']}")
    print(
        "quality: "
        f"matched={report['matched_responses']} stale={report['stale_responses_ignored']} "
        f"timeouts={report['timeouts']} trades={report['trades_executed']} "
        f"malformed={report['malformed_journals']} missing={report['missing_required_field_journals']}"
    )
    print(
        "raw_action BUY/SELL/HOLD: "
        f"{report['raw_action_counts']['BUY']}/{report['raw_action_counts']['SELL']}/{report['raw_action_counts']['HOLD']}"
    )
    print(
        "final_action BUY/SELL/HOLD: "
        f"{report['final_action_counts']['BUY']}/{report['final_action_counts']['SELL']}/{report['final_action_counts']['HOLD']}"
    )
    print(f"raw BUY->HOLD: {report['raw_buy_to_hold']}")
    print(f"raw SELL->HOLD: {report['raw_sell_to_hold']}")
    print(
        "spread_pips min/p25/p50/p75/p95/max/avg: "
        f"{spread['min']}/{spread['p25']}/{spread['p50']}/{spread['p75']}/{spread['p95']}/{spread['max']}/{spread['avg']}"
    )
    print(
        f"spread <= {report['spread_threshold_pips']}: "
        f"{spread['at_or_below_threshold_count']} ({spread['at_or_below_threshold_pct']:.1%})"
    )
    print("session spread p50/p75/count/tradable:")
    for session in report["sessions"]:
        print(
            f"  {session['session']}: "
            f"{session['p50']}/{session['p75']}/{session['observation_count']}/{session['tradable_candidate']}"
        )
    print("best local hours by p75:")
    for hour in report["best_hours_by_p75"]:
        print(
            f"  {hour['hour']:02d}:00 "
            f"session={hour['session']} p50={hour['p50']} p75={hour['p75']} "
            f"count={hour['observation_count']} tradable={hour['tradable_candidate']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze v0.26.0 spread regime readiness.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--historical-csv")
    parser.add_argument("--symbol-info")
    parser.add_argument("--symbol", default="GOLD_")
    parser.add_argument("--timeframe")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    parser.add_argument("--spread-threshold", type=float, default=DEFAULT_SPREAD_THRESHOLD)
    parser.add_argument("--p75-threshold", type=float, default=DEFAULT_P75_THRESHOLD)
    parser.add_argument("--unsuitable-p50", type=float, default=DEFAULT_UNSUITABLE_P50)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
