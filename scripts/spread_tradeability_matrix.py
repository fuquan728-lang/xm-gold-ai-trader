from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.observation_journal import safe_float
from scripts.spread_regime_report import (
    default_pip_size,
    default_point,
    load_symbol_metadata,
    numeric_summary,
    parse_historical_timestamp,
)


MODE = "spread_tradeability_matrix"
CAMPAIGN_VERSION = "v0.26.0"

DEFAULT_CSV_GLOB = "data/*_m15.csv"
DEFAULT_TIMEFRAMES = ("M15", "H1", "H4")
TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


@dataclass(frozen=True)
class CsvSpec:
    path: Path
    symbol: str
    point: float | None = None
    pip_size: float | None = None
    spread_override_pips: float | None = None


def main() -> int:
    args = parse_args()
    specs = discover_csv_specs(
        csv_paths=[Path(item) for item in args.csv],
        csv_glob=args.csv_glob,
        overrides=parse_spread_overrides(args.assume_spread_pips),
    )
    report = build_tradeability_matrix(
        specs,
        timeframes=parse_timeframes(args.timeframes),
        min_bars=args.min_bars,
        absolute_spread_p50_pips=args.absolute_spread_p50_pips,
        absolute_spread_p75_pips=args.absolute_spread_p75_pips,
        max_spread_to_range_p50_pct=args.max_spread_to_range_p50_pct,
        max_spread_to_range_p75_pct=args.max_spread_to_range_p75_pct,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0


def build_tradeability_matrix(
    specs: Iterable[CsvSpec],
    *,
    timeframes: Iterable[str] = DEFAULT_TIMEFRAMES,
    min_bars: int = 100,
    absolute_spread_p50_pips: float = 3.0,
    absolute_spread_p75_pips: float = 3.5,
    max_spread_to_range_p50_pct: float = 15.0,
    max_spread_to_range_p75_pct: float = 25.0,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in specs:
        base_bars = load_csv_bars(spec)
        for timeframe in timeframes:
            aggregated = aggregate_bars(base_bars, timeframe)
            row = summarize_tradeability(
                spec=spec,
                timeframe=timeframe,
                bars=aggregated,
                min_bars=min_bars,
                absolute_spread_p50_pips=absolute_spread_p50_pips,
                absolute_spread_p75_pips=absolute_spread_p75_pips,
                max_spread_to_range_p50_pct=max_spread_to_range_p50_pct,
                max_spread_to_range_p75_pct=max_spread_to_range_p75_pct,
            )
            rows.append(row)

    candidates = [
        row
        for row in rows
        if row["status"] == "SPREAD_AND_COST_CANDIDATE"
    ]
    research_candidates = [
        row
        for row in rows
        if row["status"] == "LONGER_TIMEFRAME_RESEARCH_CANDIDATE"
    ]
    missing = [row for row in rows if row["status"] == "MISSING_SPREAD_DATA"]
    baseline = next((row for row in rows if row["symbol"] == "GOLD_" and row["timeframe"] == "M15"), None)
    if candidates:
        status = "CANDIDATES_FOUND"
        reason = "one or more symbol/timeframe rows pass both absolute spread and spread-to-range cost gates"
    elif research_candidates:
        status = "LONGER_TIMEFRAME_RESEARCH_CANDIDATES"
        reason = "some rows fail the strict absolute spread gate but have acceptable spread-to-range cost"
    elif missing and len(missing) == len(rows):
        status = "NEEDS_REAL_SPREAD_DATA"
        reason = "all candidate CSVs have missing or zero spread data"
    else:
        status = "BLOCKED"
        reason = "no symbol/timeframe row has acceptable spread-to-range cost"

    return {
        "project": "xm-gold-ai-trader",
        "mode": MODE,
        "campaign_version": CAMPAIGN_VERSION,
        "status": status,
        "reason": reason,
        "min_bars": min_bars,
        "absolute_spread_gate": {
            "max_p50_pips": absolute_spread_p50_pips,
            "max_p75_pips": absolute_spread_p75_pips,
        },
        "cost_gate": {
            "max_spread_to_range_p50_pct": max_spread_to_range_p50_pct,
            "max_spread_to_range_p75_pct": max_spread_to_range_p75_pct,
        },
        "baseline_gold_m15": baseline,
        "matrix": rows,
        "best_candidates": best_candidates(rows, limit=8),
        "research_candidates": best_research_candidates(research_candidates, limit=8),
        "missing_spread_data": [
            {
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "source_path": row["source_path"],
                "reason": row["reason"],
            }
            for row in missing
        ],
        "next_actions": next_actions(baseline, candidates, research_candidates, missing),
    }


def discover_csv_specs(
    *,
    csv_paths: list[Path],
    csv_glob: str,
    overrides: Mapping[str, float],
) -> list[CsvSpec]:
    paths = csv_paths or sorted(Path(".").glob(csv_glob))
    specs: list[CsvSpec] = []
    for path in paths:
        metadata = load_symbol_metadata(path.with_suffix(path.suffix + ".symbol_info.json"))
        symbol = infer_symbol(path, metadata)
        symbol_info = (metadata or {}).get("symbol_info") if metadata else None
        point = safe_float((symbol_info or {}).get("point")) if isinstance(symbol_info, Mapping) else None
        override = overrides.get(symbol.upper())
        specs.append(
            CsvSpec(
                path=path,
                symbol=symbol,
                point=point,
                pip_size=None,
                spread_override_pips=override,
            )
        )
    return specs


def load_csv_bars(spec: CsvSpec) -> list[dict[str, Any]]:
    point = spec.point or default_point(spec.symbol)
    pip_size = spec.pip_size or default_pip_size(spec.symbol)
    bars: list[dict[str, Any]] = []
    with spec.path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            timestamp = parse_historical_timestamp(row.get("time"))
            high = safe_float(row.get("high"))
            low = safe_float(row.get("low"))
            open_price = safe_float(row.get("open"))
            close = safe_float(row.get("close"))
            spread_points = safe_float(row.get("spread"))
            if timestamp is None or high is None or low is None or open_price is None or close is None:
                continue
            if spec.spread_override_pips is not None:
                spread_pips = spec.spread_override_pips
                spread_source = "override"
            elif spread_points is not None:
                spread_pips = spread_points * point / pip_size
                spread_source = "csv_spread_points"
            else:
                spread_pips = None
                spread_source = "missing"
            bars.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "spread_pips": spread_pips,
                    "spread_source": spread_source,
                    "range_pips": (high - low) / pip_size,
                }
            )
    return sorted(bars, key=lambda item: item["timestamp"])


def aggregate_bars(base_bars: list[Mapping[str, Any]], timeframe: str) -> list[dict[str, Any]]:
    minutes = TIMEFRAME_MINUTES[timeframe]
    buckets: dict[Any, list[Mapping[str, Any]]] = {}
    for bar in base_bars:
        timestamp = bar["timestamp"]
        bucket = floor_time(timestamp, minutes)
        buckets.setdefault(bucket, []).append(bar)

    aggregated: list[dict[str, Any]] = []
    for bucket, rows in sorted(buckets.items(), key=lambda item: item[0]):
        spreads = [safe_float(row.get("spread_pips")) for row in rows]
        clean_spreads = sorted(value for value in spreads if value is not None and not math.isnan(value))
        spread_pips = quantile(clean_spreads, 0.5) if clean_spreads else None
        high = max(float(row["high"]) for row in rows)
        low = min(float(row["low"]) for row in rows)
        pip_size = infer_pip_size_from_range(rows)
        range_pips = (high - low) / pip_size if pip_size else None
        aggregated.append(
            {
                "timestamp": bucket,
                "open": float(rows[0]["open"]),
                "high": high,
                "low": low,
                "close": float(rows[-1]["close"]),
                "spread_pips": spread_pips,
                "range_pips": range_pips,
                "source_bar_count": len(rows),
                "spread_source": rows[0].get("spread_source"),
            }
        )
    return aggregated


def summarize_tradeability(
    *,
    spec: CsvSpec,
    timeframe: str,
    bars: list[Mapping[str, Any]],
    min_bars: int,
    absolute_spread_p50_pips: float,
    absolute_spread_p75_pips: float,
    max_spread_to_range_p50_pct: float,
    max_spread_to_range_p75_pct: float,
) -> dict[str, Any]:
    spreads = [safe_float(bar.get("spread_pips")) for bar in bars]
    ranges = [safe_float(bar.get("range_pips")) for bar in bars]
    ratios = [
        (spread / range_pips) * 100.0
        for spread, range_pips in zip(spreads, ranges)
        if spread is not None and range_pips is not None and range_pips > 0
    ]
    positive_spreads = [spread for spread in spreads if spread is not None and spread > 0]
    spread_quality = "OK"
    if spec.spread_override_pips is not None:
        spread_quality = "SPREAD_OVERRIDE"
    elif not positive_spreads:
        spread_quality = "MISSING_OR_ZERO_SPREAD"

    spread_summary = numeric_summary(spreads, None)
    range_summary = numeric_summary(ranges, None)
    ratio_summary = numeric_summary(ratios, None)
    status, reason = decide_row_status(
        count=len(bars),
        min_bars=min_bars,
        spread_quality=spread_quality,
        spread_summary=spread_summary,
        ratio_summary=ratio_summary,
        absolute_spread_p50_pips=absolute_spread_p50_pips,
        absolute_spread_p75_pips=absolute_spread_p75_pips,
        max_spread_to_range_p50_pct=max_spread_to_range_p50_pct,
        max_spread_to_range_p75_pct=max_spread_to_range_p75_pct,
    )
    spread_gate_pass = None
    if spread_quality != "MISSING_OR_ZERO_SPREAD":
        spread_gate_pass = absolute_spread_gate_pass(
            spread_summary,
            absolute_spread_p50_pips=absolute_spread_p50_pips,
            absolute_spread_p75_pips=absolute_spread_p75_pips,
        )
    return {
        "symbol": spec.symbol,
        "timeframe": timeframe,
        "source_path": str(spec.path),
        "status": status,
        "reason": reason,
        "spread_data_quality": spread_quality,
        "bar_count": len(bars),
        "absolute_spread_gate_pass": spread_gate_pass,
        "spread_pips": spread_summary,
        "range_pips": range_summary,
        "spread_to_range_pct": ratio_summary,
    }


def decide_row_status(
    *,
    count: int,
    min_bars: int,
    spread_quality: str,
    spread_summary: Mapping[str, Any],
    ratio_summary: Mapping[str, Any],
    absolute_spread_p50_pips: float,
    absolute_spread_p75_pips: float,
    max_spread_to_range_p50_pct: float,
    max_spread_to_range_p75_pct: float,
) -> tuple[str, str]:
    if count < min_bars:
        return ("INSUFFICIENT_BARS", f"bar_count={count} < min_bars={min_bars}")
    if spread_quality == "MISSING_OR_ZERO_SPREAD":
        return ("MISSING_SPREAD_DATA", "spread column is missing or all zero; collect real MT5 spread first")
    p50 = ratio_summary.get("p50")
    p75 = ratio_summary.get("p75")
    if p50 is None or p75 is None:
        return ("INSUFFICIENT_RANGE_DATA", "range or spread-to-range data is unavailable")
    cost_pass = p50 <= max_spread_to_range_p50_pct and p75 <= max_spread_to_range_p75_pct
    spread_pass = absolute_spread_gate_pass(
        spread_summary,
        absolute_spread_p50_pips=absolute_spread_p50_pips,
        absolute_spread_p75_pips=absolute_spread_p75_pips,
    )
    spread_p50 = spread_summary.get("p50")
    spread_p75 = spread_summary.get("p75")
    if spread_pass and cost_pass:
        return (
            "SPREAD_AND_COST_CANDIDATE",
            f"absolute spread and spread/range gates pass; cost p50={p50:.2f}% p75={p75:.2f}%",
        )
    if cost_pass:
        return (
            "LONGER_TIMEFRAME_RESEARCH_CANDIDATE",
            "absolute spread gate fails but spread/range cost is acceptable; "
            f"spread p50={spread_p50:.2f} p75={spread_p75:.2f}, cost p50={p50:.2f}% p75={p75:.2f}%",
        )
    if spread_pass:
        return (
            "LOW_SPREAD_BUT_LOW_RANGE",
            f"absolute spread gate passes but spread/range p50={p50:.2f}% or p75={p75:.2f}% is too high",
        )
    return (
        "BLOCKED_BY_SPREAD_COST",
        "absolute spread and spread/range gates both fail; "
        f"spread p50={spread_p50:.2f} p75={spread_p75:.2f}, cost p50={p50:.2f}% p75={p75:.2f}%",
    )


def absolute_spread_gate_pass(
    spread_summary: Mapping[str, Any],
    *,
    absolute_spread_p50_pips: float,
    absolute_spread_p75_pips: float,
) -> bool:
    p50 = spread_summary.get("p50")
    p75 = spread_summary.get("p75")
    return (
        p50 is not None
        and p75 is not None
        and p50 <= absolute_spread_p50_pips
        and p75 <= absolute_spread_p75_pips
    )


def best_candidates(rows: list[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    ranked = [
        row
        for row in rows
        if row.get("spread_to_range_pct", {}).get("p50") is not None
        and row.get("status") != "MISSING_SPREAD_DATA"
    ]
    ranked.sort(
        key=lambda row: (
            row["status"] != "SPREAD_AND_COST_CANDIDATE",
            row["spread_to_range_pct"]["p50"],
            row["spread_to_range_pct"]["p75"],
        )
    )
    return [
        {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "status": row["status"],
            "spread_pips_p50": row["spread_pips"]["p50"],
            "range_pips_p50": row["range_pips"]["p50"],
            "spread_to_range_p50_pct": row["spread_to_range_pct"]["p50"],
            "spread_to_range_p75_pct": row["spread_to_range_pct"]["p75"],
        }
        for row in ranked[:limit]
    ]


def best_research_candidates(rows: list[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    ranked = [
        row
        for row in rows
        if row.get("spread_to_range_pct", {}).get("p50") is not None
    ]
    ranked.sort(key=lambda row: (row["spread_to_range_pct"]["p50"], row["spread_to_range_pct"]["p75"]))
    return [
        {
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "status": row["status"],
            "absolute_spread_gate_pass": row["absolute_spread_gate_pass"],
            "spread_pips_p50": row["spread_pips"]["p50"],
            "spread_pips_p75": row["spread_pips"]["p75"],
            "range_pips_p50": row["range_pips"]["p50"],
            "spread_to_range_p50_pct": row["spread_to_range_pct"]["p50"],
            "spread_to_range_p75_pct": row["spread_to_range_pct"]["p75"],
        }
        for row in ranked[:limit]
    ]


def next_actions(
    baseline: Mapping[str, Any] | None,
    candidates: list[Mapping[str, Any]],
    research_candidates: list[Mapping[str, Any]],
    missing: list[Mapping[str, Any]],
) -> list[str]:
    actions: list[str] = []
    if baseline and baseline.get("absolute_spread_gate_pass") is False:
        actions.append("Keep the current strict spread gate blocked; do not loosen it to force trades.")
    if candidates:
        actions.append("Study candidate rows with dry-run only before any strategy or execution change.")
    if research_candidates:
        actions.append("Use longer-timeframe candidates as research hypotheses, not live-trade permission.")
    if missing:
        actions.append("Collect real MT5 spread metadata/journals for symbols with missing or zero spread data.")
    if not candidates:
        actions.append("Compare lower-spread account data before changing any production threshold.")
    return actions


def floor_time(timestamp: Any, minutes: int) -> Any:
    if minutes >= 1440:
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    total_minutes = timestamp.hour * 60 + timestamp.minute
    bucket_minutes = (total_minutes // minutes) * minutes
    return timestamp.replace(
        hour=bucket_minutes // 60,
        minute=bucket_minutes % 60,
        second=0,
        microsecond=0,
    )


def infer_pip_size_from_range(rows: list[Mapping[str, Any]]) -> float | None:
    ranges = [safe_float(row.get("range_pips")) for row in rows]
    raw_ranges = [
        (safe_float(row.get("high")), safe_float(row.get("low")), safe_float(row.get("range_pips")))
        for row in rows
    ]
    for high, low, range_pips in raw_ranges:
        if high is not None and low is not None and range_pips is not None and range_pips > 0:
            return (high - low) / range_pips
    return None


def infer_symbol(path: Path, metadata: Mapping[str, Any] | None) -> str:
    if metadata and metadata.get("symbol"):
        return str(metadata["symbol"])
    stem = path.stem.lower()
    if "gold" in stem:
        return "GOLD_"
    if "xau" in stem:
        return "XAUUSD"
    if "eurusd" in stem:
        return "EURUSD"
    if "gbpusd" in stem:
        return "GBPUSD"
    return stem.split("_")[0].upper()


def parse_spread_overrides(values: list[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--assume-spread-pips must use SYMBOL=PIPS format")
        symbol, raw = value.split("=", 1)
        overrides[symbol.strip().upper()] = float(raw)
    return overrides


def parse_timeframes(value: str) -> list[str]:
    timeframes = [item.strip().upper() for item in value.split(",") if item.strip()]
    invalid = [item for item in timeframes if item not in TIMEFRAME_MINUTES]
    if invalid:
        raise ValueError(f"unsupported timeframe(s): {', '.join(invalid)}")
    return timeframes


def quantile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        raise ValueError("quantile requires at least one value")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * pct
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader spread tradeability matrix")
    print(f"campaign: {report['campaign_version']}")
    print(f"status: {report['status']}")
    print(f"reason: {report['reason']}")
    baseline = report.get("baseline_gold_m15")
    if baseline:
        print(
            "baseline GOLD_ M15: "
            f"{baseline['status']} | spread_p50={baseline['spread_pips']['p50']} "
            f"spread_p75={baseline['spread_pips']['p75']} "
            f"range_p50={baseline['range_pips']['p50']} "
            f"cost_p50={baseline['spread_to_range_pct']['p50']}% "
            f"absolute_gate={baseline['absolute_spread_gate_pass']}"
        )
    print("matrix:")
    for row in report["matrix"]:
        ratio = row["spread_to_range_pct"]
        print(
            f"  {row['symbol']} {row['timeframe']}: {row['status']} | "
            f"spread_quality={row['spread_data_quality']} | absolute_gate={row['absolute_spread_gate_pass']} | "
            f"bars={row['bar_count']} | "
            f"spread_p50={row['spread_pips']['p50']} | range_p50={row['range_pips']['p50']} | "
            f"cost_p50={ratio['p50']}% cost_p75={ratio['p75']}%"
        )
    if report["best_candidates"]:
        print("best candidates:")
        for row in report["best_candidates"]:
            print(
                f"  {row['symbol']} {row['timeframe']}: {row['status']} | "
                f"cost_p50={row['spread_to_range_p50_pct']}% cost_p75={row['spread_to_range_p75_pct']}%"
            )
    if report["research_candidates"]:
        print("longer-timeframe research candidates:")
        for row in report["research_candidates"]:
            print(
                f"  {row['symbol']} {row['timeframe']}: "
                f"spread_p50={row['spread_pips_p50']} spread_p75={row['spread_pips_p75']} "
                f"cost_p50={row['spread_to_range_p50_pct']}% cost_p75={row['spread_to_range_p75_pct']}%"
            )
    print("next:")
    for action in report["next_actions"]:
        print(f"  - {action}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare spread tradeability across symbols and longer timeframes.")
    parser.add_argument("--csv", action="append", default=[], help="Historical CSV path. Repeat to compare symbols.")
    parser.add_argument("--csv-glob", default=DEFAULT_CSV_GLOB, help="Used when --csv is omitted.")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES))
    parser.add_argument("--min-bars", type=int, default=100)
    parser.add_argument("--absolute-spread-p50-pips", type=float, default=3.0)
    parser.add_argument("--absolute-spread-p75-pips", type=float, default=3.5)
    parser.add_argument("--max-spread-to-range-p50-pct", type=float, default=15.0)
    parser.add_argument("--max-spread-to-range-p75-pct", type=float, default=25.0)
    parser.add_argument(
        "--assume-spread-pips",
        action="append",
        default=[],
        help="Lower-spread account scenario, SYMBOL=PIPS. Example: --assume-spread-pips GOLD_=2.5",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
