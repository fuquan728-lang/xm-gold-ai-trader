from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.observation_journal import DEFAULT_JOURNAL_DIR, iter_observations, normalize_action, safe_float


MODE = "signal_quality_without_spread_report"
CAMPAIGN_VERSION = "v0.26.1"
IGNORED_BLOCKS = {"SPREAD_TOO_HIGH", "ACTION_HOLD"}
HARD_BLOCKS = {"LOW_CONFIDENCE", "INDICATOR_QUALITY_GATE", "SAFETY_GATE", "MISSING_REQUEST_ID"}


def main() -> int:
    args = parse_args()
    report = build_signal_quality_without_spread_report(
        iter_observations(args.journal_dir),
        symbol=args.symbol,
        timeframe=args.timeframe,
        target=args.target,
        confidence_threshold=args.confidence_threshold,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0


def build_signal_quality_without_spread_report(
    observations: Iterable[Mapping[str, Any]],
    *,
    symbol: str = "GOLD_",
    timeframe: str = "M5",
    target: int = 100,
    confidence_threshold: float = 0.65,
) -> dict[str, Any]:
    rows = []
    malformed = 0
    for row in observations:
        payload = dict(row)
        if payload.get("_malformed"):
            malformed += 1
            continue
        if payload.get("symbol") != symbol or payload.get("timeframe") != timeframe:
            continue
        rows.append(payload)

    total = len(rows)
    matched = sum(1 for row in rows if row.get("response_matched") is True)
    stale = sum(1 for row in rows if row.get("stale_response") is True)
    timeouts = sum(1 for row in rows if row.get("timeout") is True)
    trades = sum(1 for row in rows if row.get("trade_executed") is True)
    journal_quality_pass = (
        total > 0 and matched == total and stale == 0 and timeouts == 0 and trades == 0 and malformed == 0
    )

    raw_counter = Counter(normalize_action(row.get("ai_action_raw")) for row in rows)
    final_counter = Counter(normalize_action(row.get("ai_action_final")) for row in rows)
    all_block_counter: Counter[str] = Counter()
    non_spread_block_counter: Counter[str] = Counter()

    directional_rows = []
    candidates = []
    rejected_directional = []
    for row in rows:
        raw_action = normalize_action(row.get("ai_action_raw"))
        blocks = [str(item) for item in (row.get("blocked_by") or [])]
        all_block_counter.update(blocks)
        non_spread_blocks = [block for block in blocks if block not in IGNORED_BLOCKS]
        non_spread_block_counter.update(non_spread_blocks)
        confidence = safe_float(row.get("confidence")) or 0.0
        if raw_action not in {"BUY", "SELL"}:
            continue
        enriched = dict(row)
        enriched["_raw_action"] = raw_action
        enriched["_confidence"] = confidence
        enriched["_non_spread_blocks"] = non_spread_blocks
        directional_rows.append(enriched)
        if confidence >= confidence_threshold and not non_spread_blocks:
            candidates.append(enriched)
        else:
            rejected_directional.append(enriched)

    status, reason = decide_status(
        total=total,
        target=target,
        journal_quality_pass=journal_quality_pass,
        candidates=candidates,
        directional_rows=directional_rows,
    )

    return {
        "project": "xm-gold-ai-trader",
        "mode": MODE,
        "campaign_version": CAMPAIGN_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "target": target,
        "status": status,
        "reason": reason,
        "rule": "counterfactual research only: ignore SPREAD_TOO_HIGH and final ACTION_HOLD marker; keep confidence and hard safety gates",
        "confidence_threshold": confidence_threshold,
        "total_observations": total,
        "target_met": total >= target,
        "journal_quality_pass": journal_quality_pass,
        "matched_responses": matched,
        "stale_responses_ignored": stale,
        "timeouts": timeouts,
        "trades_executed": trades,
        "malformed_journals": malformed,
        "raw_action_counts": action_counts(raw_counter),
        "final_action_counts": action_counts(final_counter),
        "all_blocked_by_counts": dict(sorted(all_block_counter.items())),
        "non_spread_blocked_by_counts": dict(sorted(non_spread_block_counter.items())),
        "directional_raw_signals": len(directional_rows),
        "directional_raw_signal_rate": ratio(len(directional_rows), total),
        "counterfactual_candidates_without_spread": len(candidates),
        "counterfactual_candidate_rate": ratio(len(candidates), total),
        "candidate_action_counts": action_counts(Counter(row["_raw_action"] for row in candidates)),
        "rejected_directional_without_spread": len(rejected_directional),
        "rejected_directional_reasons": rejected_reasons(rejected_directional, confidence_threshold),
        "candidate_examples": examples(candidates, limit=5),
    }


def decide_status(
    *,
    total: int,
    target: int,
    journal_quality_pass: bool,
    candidates: list[Mapping[str, Any]],
    directional_rows: list[Mapping[str, Any]],
) -> tuple[str, str]:
    if total < target:
        return ("IN_PROGRESS", f"total_observations={total} < target={target}")
    if not journal_quality_pass:
        return ("FAIL", "journal quality failed; do not evaluate signal quality")
    if candidates:
        return (
            "SIGNAL_CANDIDATES_FOUND",
            f"{len(candidates)} raw directional signals remain after ignoring spread and keeping hard gates",
        )
    if directional_rows:
        return (
            "DIRECTIONAL_BUT_LOW_QUALITY",
            "raw BUY/SELL exists, but all are blocked by confidence or non-spread quality gates",
        )
    return ("NO_DIRECTIONAL_SIGNAL", "no raw BUY/SELL signals in the selected sample")


def rejected_reasons(rows: list[Mapping[str, Any]], confidence_threshold: float) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        row_reasons = set(row["_non_spread_blocks"])
        if row["_confidence"] < confidence_threshold:
            row_reasons.add("LOW_CONFIDENCE")
        for block in row_reasons:
            counter[block] += 1
    return dict(sorted(counter.items()))


def examples(rows: list[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": row.get("timestamp"),
            "request_id": row.get("request_id"),
            "raw_action": row.get("_raw_action"),
            "confidence": row.get("_confidence"),
            "spread_pips": safe_float(row.get("spread_pips")),
            "rsi": safe_float(row.get("rsi")),
            "macd_main": safe_float(row.get("macd_main")),
            "macd_signal": safe_float(row.get("macd_signal")),
            "ema50": safe_float(row.get("ema50")),
        }
        for row in rows[:limit]
    ]


def action_counts(counter: Counter[str]) -> dict[str, int]:
    return {"BUY": counter["BUY"], "SELL": counter["SELL"], "HOLD": counter["HOLD"]}


def ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def print_summary(report: Mapping[str, Any]) -> None:
    print("xm-gold-ai-trader signal quality without spread report")
    print(f"campaign: {report['campaign_version']}")
    print(f"symbol/timeframe: {report['symbol']} {report['timeframe']}")
    print(f"status: {report['status']}")
    print(f"reason: {report['reason']}")
    print(f"total_observations: {report['total_observations']} / {report['target']}")
    print(f"journal_quality_pass: {report['journal_quality_pass']}")
    print(
        "quality: "
        f"matched={report['matched_responses']} stale={report['stale_responses_ignored']} "
        f"timeouts={report['timeouts']} trades={report['trades_executed']} malformed={report['malformed_journals']}"
    )
    print(
        "raw_action BUY/SELL/HOLD: "
        f"{report['raw_action_counts']['BUY']}/{report['raw_action_counts']['SELL']}/{report['raw_action_counts']['HOLD']}"
    )
    print(
        "final_action BUY/SELL/HOLD: "
        f"{report['final_action_counts']['BUY']}/{report['final_action_counts']['SELL']}/{report['final_action_counts']['HOLD']}"
    )
    print(f"directional_raw_signals: {report['directional_raw_signals']} ({report['directional_raw_signal_rate']:.1%})")
    print(
        "counterfactual_candidates_without_spread: "
        f"{report['counterfactual_candidates_without_spread']} ({report['counterfactual_candidate_rate']:.1%})"
    )
    print(
        "candidate BUY/SELL/HOLD: "
        f"{report['candidate_action_counts']['BUY']}/{report['candidate_action_counts']['SELL']}/{report['candidate_action_counts']['HOLD']}"
    )
    print(f"non_spread_blocked_by_counts: {report['non_spread_blocked_by_counts']}")
    print(f"rejected_directional_reasons: {report['rejected_directional_reasons']}")
    if report["candidate_examples"]:
        print("candidate examples:")
        for row in report["candidate_examples"]:
            print(
                f"  {row['timestamp']} {row['raw_action']} conf={row['confidence']} "
                f"rsi={row['rsi']} macd={row['macd_main']}/{row['macd_signal']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Counterfactual M5 signal quality report that ignores spread blocks.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--symbol", default="GOLD_")
    parser.add_argument("--timeframe", default="M5")
    parser.add_argument("--target", type=int, default=100)
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
