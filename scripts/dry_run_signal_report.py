from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_dry_run_signal_journal import (
    DEFAULT_JOURNAL_DIR,
    JOURNAL_SCHEMA_VERSION,
    MODE,
    PROJECT,
)
from src.broker.execution_safety import REASON_EMERGENCY_STOP_FILE_PRESENT
from src.strategy.risk_manager import REASON_LOT_BELOW_VOLUME_MIN


REASON_JOURNAL_JSON_INVALID = "JOURNAL_JSON_INVALID"
REASON_JOURNAL_NOT_OBJECT = "JOURNAL_NOT_OBJECT"
REASON_JOURNAL_REQUIRED_FIELD_MISSING = "JOURNAL_REQUIRED_FIELD_MISSING"


def main() -> int:
    args = parse_args()
    report = summarize_dry_run_signals(Path(args.journal_dir))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def summarize_dry_run_signals(journal_dir: Path) -> dict[str, Any]:
    entries = load_dry_run_journals(journal_dir)
    valid_payloads = [entry["payload"] for entry in entries if entry["payload"] is not None]
    malformed = [entry for entry in entries if entry["payload"] is None]
    missing_required = [
        entry for entry in entries if entry["payload"] is not None and missing_required_fields(entry["payload"])
    ]

    reason_counter: Counter[str] = Counter()
    spreads: list[float] = []
    signal_count = 0
    block_count = 0
    skip_count = 0
    risk_lot_below_min_count = 0
    emergency_stop_seen_count = 0
    observed_orders_sent_sum = 0
    bar_counter: Counter[tuple[Any, Any, Any, Any]] = Counter()

    for entry in malformed:
        reason_counter.update(entry["reason_codes"])

    for entry in missing_required:
        reason_counter.update([REASON_JOURNAL_REQUIRED_FIELD_MISSING])

    for payload in valid_payloads:
        final_decision = payload.get("final_decision")
        if final_decision == "SIGNAL":
            signal_count += 1
        elif final_decision == "BLOCK":
            block_count += 1
        elif final_decision == "SKIP":
            skip_count += 1

        codes = list(payload.get("reason_codes") or [])
        reason_counter.update(codes)
        if REASON_LOT_BELOW_VOLUME_MIN in codes or REASON_LOT_BELOW_VOLUME_MIN in (
            payload.get("risk_preview", {}).get("reason_codes") or []
        ):
            risk_lot_below_min_count += 1
        if REASON_EMERGENCY_STOP_FILE_PRESENT in codes:
            emergency_stop_seen_count += 1

        spread = numeric_or_none(payload.get("current_spread_points"))
        if spread is not None:
            spreads.append(spread)
        observed_orders_sent_sum += int(payload.get("orders_sent") or 0)
        closed_bar_key = closed_bar_identity(payload)
        if closed_bar_key is not None:
            bar_counter.update([closed_bar_key])

    total_observations = len(valid_payloads)
    duplicate_groups = {key: count for key, count in bar_counter.items() if count > 1}
    return {
        "project": PROJECT,
        "mode": "dry_run_signal_report",
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "journal_dir": str(journal_dir),
        "orders_sent": 0,
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "total_files": len(entries),
        "total_observations": total_observations,
        "signal_count": signal_count,
        "block_count": block_count,
        "skip_count": skip_count,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "avg_spread": sum(spreads) / len(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "actionable_signal_rate": signal_count / total_observations if total_observations else 0.0,
        "unique_closed_bars": len(bar_counter),
        "duplicate_observations": sum(count - 1 for count in duplicate_groups.values()),
        "duplicate_skip_count": skip_count,
        "duplicate_bar_groups": [
            {
                "symbol": key[0],
                "timeframe": key[1],
                "campaign_id": key[2],
                "latest_closed_bar_time": key[3],
                "count": count,
            }
            for key, count in sorted(duplicate_groups.items(), key=lambda item: str(item[0]))
        ],
        "risk_lot_below_min_count": risk_lot_below_min_count,
        "emergency_stop_seen_count": emergency_stop_seen_count,
        "malformed_journals": len(malformed),
        "missing_required_field_journals": len(missing_required),
        "malformed_details": [
            {
                "path": entry["path"],
                "reason_codes": entry["reason_codes"],
                "error": entry["error"],
            }
            for entry in malformed
        ],
    }


def load_dry_run_journals(journal_dir: Path) -> list[dict[str, Any]]:
    if not journal_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(journal_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_JOURNAL_JSON_INVALID],
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(payload, dict):
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_JOURNAL_NOT_OBJECT],
                    "error": "journal JSON root is not an object",
                }
            )
            continue
        entries.append({"path": str(path), "payload": payload, "reason_codes": [], "error": None})
    return entries


def missing_required_fields(payload: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("journal_schema_version", "project", "mode", "timestamp_utc", "final_decision", "orders_sent"):
        if field not in payload:
            missing.append(field)
    if payload.get("mode") not in {MODE, f"{MODE}_loop"}:
        missing.append("mode")
    if "reason_codes" not in payload:
        missing.append("reason_codes")
    return missing


def numeric_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def closed_bar_identity(payload: Mapping[str, Any]) -> tuple[Any, Any, Any, Any] | None:
    closed_bar_time = payload.get("latest_closed_bar_time")
    if not closed_bar_time:
        return None
    symbol_payload = payload.get("symbol")
    symbol = symbol_payload.get("name") if isinstance(symbol_payload, Mapping) else None
    config = payload.get("config")
    if symbol is None and isinstance(config, Mapping):
        symbol = config.get("symbol")
    return (symbol, payload.get("timeframe"), payload.get("campaign_id"), closed_bar_time)


def print_summary(report: dict[str, Any]) -> None:
    print("xm-gold-ai-trader dry-run signal report")
    print(f"total observations: {report['total_observations']}")
    print(f"signals: {report['signal_count']}")
    print(f"blocks: {report['block_count']}")
    print(f"skips: {report['skip_count']}")
    print(f"unique closed bars: {report['unique_closed_bars']}")
    print(f"duplicate observations: {report['duplicate_observations']}")
    print(f"avg spread: {report['avg_spread']}")
    print(f"max spread: {report['max_spread']}")
    print(f"actionable signal rate: {report['actionable_signal_rate']:.4f}")
    print(f"malformed journals: {report['malformed_journals']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize live dry-run signal journals.")
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
