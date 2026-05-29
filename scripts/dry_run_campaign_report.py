from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dry_run_signal_report import load_dry_run_journals, numeric_or_none
from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, PROJECT, REASON_SKIP_DUPLICATE_BAR
from scripts.run_dry_observation_campaign import DEFAULT_CAMPAIGN_DIR


REASON_CAMPAIGN_JSON_INVALID = "CAMPAIGN_JSON_INVALID"
REASON_CAMPAIGN_NOT_OBJECT = "CAMPAIGN_NOT_OBJECT"
REASON_JOURNAL_MISSING_CAMPAIGN_ID = "JOURNAL_MISSING_CAMPAIGN_ID"


def main() -> int:
    args = parse_args()
    report = summarize_campaigns(
        campaign_dir=Path(args.campaign_dir),
        journal_dir=Path(args.journal_dir),
        campaign_id=args.campaign_id,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print_summary(report)
    return 0


def summarize_campaigns(
    *,
    campaign_dir: Path,
    journal_dir: Path,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    campaign_entries = load_campaign_metadata(campaign_dir, campaign_id=campaign_id)
    journal_entries = load_dry_run_journals(journal_dir)
    valid_campaigns = [entry["payload"] for entry in campaign_entries if entry["payload"] is not None]
    malformed_campaigns = [entry for entry in campaign_entries if entry["payload"] is None]
    valid_journals = [entry["payload"] for entry in journal_entries if entry["payload"] is not None]
    malformed_journals = [entry for entry in journal_entries if entry["payload"] is None]

    metadata_campaign_ids = {str(payload.get("campaign_id")) for payload in valid_campaigns if payload.get("campaign_id")}
    journal_campaign_ids = {str(payload.get("campaign_id")) for payload in valid_journals if payload.get("campaign_id")}
    campaign_ids = [campaign_id] if campaign_id else sorted(metadata_campaign_ids | journal_campaign_ids)

    campaign_summaries = [
        summarize_single_campaign(
            campaign_id=current_id,
            metadata=first_matching_campaign(valid_campaigns, current_id),
            journals=[payload for payload in valid_journals if payload.get("campaign_id") == current_id],
        )
        for current_id in campaign_ids
    ]

    unlinked_observations = [
        payload
        for payload in valid_journals
        if not payload.get("campaign_id") and (campaign_id is None or payload.get("campaign_id") == campaign_id)
    ]
    reason_counter: Counter[str] = Counter()
    for summary in campaign_summaries:
        reason_counter.update(summary["reason_code_counts"])
    if unlinked_observations:
        reason_counter.update({REASON_JOURNAL_MISSING_CAMPAIGN_ID: len(unlinked_observations)})
    for entry in malformed_campaigns + malformed_journals:
        reason_counter.update(entry["reason_codes"])

    total_observations = sum(int(summary["total_observations"]) for summary in campaign_summaries)
    signal_count = sum(int(summary["signal_count"]) for summary in campaign_summaries)
    block_count = sum(int(summary["block_count"]) for summary in campaign_summaries)
    duplicate_skip_count = sum(int(summary["duplicate_skip_count"]) for summary in campaign_summaries)
    unique_closed_bars = sum(int(summary["unique_closed_bars"]) for summary in campaign_summaries)
    duplicate_observations = sum(int(summary["duplicate_observations"]) for summary in campaign_summaries)
    observed_orders_sent_sum = sum(int(summary["observed_orders_sent_sum"]) for summary in campaign_summaries)
    spreads = [
        spread
        for summary in campaign_summaries
        for spread in summary.get("_spreads", [])
    ]

    public_summaries = [{key: value for key, value in summary.items() if key != "_spreads"} for summary in campaign_summaries]
    return {
        "project": PROJECT,
        "mode": "dry_run_campaign_report",
        "campaign_dir": str(campaign_dir),
        "journal_dir": str(journal_dir),
        "campaign_id": campaign_id,
        "orders_sent": 0,
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "campaigns_total": len(public_summaries),
        "campaigns": public_summaries,
        "total_observations": total_observations,
        "unique_closed_bars": unique_closed_bars,
        "duplicate_observations": duplicate_observations,
        "duplicate_skip_count": duplicate_skip_count,
        "observations_by_session": aggregate_sessions(public_summaries),
        "signal_count": signal_count,
        "block_count": block_count,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "avg_spread": sum(spreads) / len(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "actionable_signal_rate": signal_count / total_observations if total_observations else 0.0,
        "unlinked_observation_count": len(unlinked_observations),
        "malformed_campaigns": len(malformed_campaigns),
        "malformed_journals": len(malformed_journals),
        "malformed_details": [
            {"path": entry["path"], "reason_codes": entry["reason_codes"], "error": entry["error"]}
            for entry in malformed_campaigns + malformed_journals
        ],
    }


def summarize_single_campaign(
    *,
    campaign_id: str,
    metadata: Mapping[str, Any] | None,
    journals: list[Mapping[str, Any]],
) -> dict[str, Any]:
    reason_counter: Counter[str] = Counter()
    session_counter: dict[str, dict[str, Any]] = {
        "Asia": empty_session(),
        "London": empty_session(),
        "NewYork": empty_session(),
        "OffHours": empty_session(),
    }
    spreads: list[float] = []
    signal_count = 0
    block_count = 0
    observed_orders_sent_sum = 0
    bar_counter: Counter[tuple[Any, Any, Any, Any]] = Counter()
    for payload in journals:
        final = payload.get("final_decision")
        if final == "SIGNAL":
            signal_count += 1
        elif final == "BLOCK":
            block_count += 1
        codes = list(payload.get("reason_codes") or [])
        reason_counter.update(codes)
        spread = numeric_or_none(payload.get("current_spread_points"))
        if spread is not None:
            spreads.append(spread)
        observed_orders_sent_sum += int(payload.get("orders_sent") or 0)
        closed_bar_key = closed_bar_identity(payload)
        if closed_bar_key is not None:
            bar_counter.update([closed_bar_key])
        session = session_name(payload.get("timestamp_utc"))
        session_counter[session]["observations"] += 1
        session_counter[session]["signals"] += 1 if final == "SIGNAL" else 0
        session_counter[session]["blocks"] += 1 if final == "BLOCK" else 0
        session_counter[session]["reason_code_counts"].update(codes)

    duplicate_skip_count = int(metadata.get("duplicate_bar_skipped") or metadata.get("skip_count") or 0) if metadata else 0
    if duplicate_skip_count:
        reason_counter.update({REASON_SKIP_DUPLICATE_BAR: duplicate_skip_count})
    duplicate_groups = {key: count for key, count in bar_counter.items() if count > 1}
    total_observations = int(metadata.get("total_poll_iterations") or metadata.get("total_iterations") or len(journals)) if metadata else len(journals)
    unique_closed_bars = len(bar_counter)
    duplicate_observations = sum(count - 1 for count in duplicate_groups.values())
    return {
        "campaign_id": campaign_id,
        "metadata_present": metadata is not None,
        "campaign_path": metadata.get("campaign_path") if metadata else None,
        "started_at_utc": metadata.get("started_at_utc") if metadata else None,
        "ended_at_utc": metadata.get("ended_at_utc") if metadata else None,
        "total_iterations": metadata.get("total_iterations") if metadata else None,
        "total_poll_iterations": metadata.get("total_poll_iterations") if metadata else None,
        "metadata_journal_count": metadata.get("journal_count") if metadata else None,
        "total_observations": total_observations,
        "journal_observations": len(journals),
        "unique_closed_bars": unique_closed_bars,
        "duplicate_observations": duplicate_observations,
        "duplicate_skip_count": duplicate_skip_count,
        "signal_count": signal_count,
        "block_count": block_count,
        "reason_code_counts": dict(sorted(reason_counter.items())),
        "avg_spread": sum(spreads) / len(spreads) if spreads else None,
        "max_spread": max(spreads) if spreads else None,
        "actionable_signal_rate": signal_count / total_observations if total_observations else 0.0,
        "observed_orders_sent_sum": observed_orders_sent_sum,
        "session_breakdown": public_session_breakdown(session_counter),
        "observations_by_session": public_session_breakdown(session_counter),
        "_spreads": spreads,
    }


def load_campaign_metadata(campaign_dir: Path, *, campaign_id: str | None = None) -> list[dict[str, Any]]:
    if not campaign_dir.exists():
        return []
    paths = [campaign_dir / f"{campaign_id}.json"] if campaign_id else sorted(campaign_dir.glob("*.json"))
    entries: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_CAMPAIGN_JSON_INVALID],
                    "error": str(exc),
                }
            )
            continue
        if not isinstance(payload, dict):
            entries.append(
                {
                    "path": str(path),
                    "payload": None,
                    "reason_codes": [REASON_CAMPAIGN_NOT_OBJECT],
                    "error": "campaign JSON root is not an object",
                }
            )
            continue
        entries.append({"path": str(path), "payload": payload, "reason_codes": [], "error": None})
    return entries


def first_matching_campaign(campaigns: list[Mapping[str, Any]], campaign_id: str) -> Mapping[str, Any] | None:
    for payload in campaigns:
        if payload.get("campaign_id") == campaign_id:
            return payload
    return None


def empty_session() -> dict[str, Any]:
    return {"observations": 0, "signals": 0, "blocks": 0, "reason_code_counts": Counter()}


def public_session_breakdown(session_counter: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        name: {
            "observations": values["observations"],
            "signals": values["signals"],
            "blocks": values["blocks"],
            "reason_code_counts": dict(sorted(values["reason_code_counts"].items())),
        }
        for name, values in session_counter.items()
    }


def aggregate_sessions(campaigns: list[Mapping[str, Any]]) -> dict[str, Any]:
    session_totals: dict[str, dict[str, Any]] = {
        "Asia": empty_session(),
        "London": empty_session(),
        "NewYork": empty_session(),
        "OffHours": empty_session(),
    }
    for campaign in campaigns:
        breakdown = campaign.get("observations_by_session") or campaign.get("session_breakdown") or {}
        if not isinstance(breakdown, Mapping):
            continue
        for name, values in breakdown.items():
            if name not in session_totals or not isinstance(values, Mapping):
                continue
            session_totals[name]["observations"] += int(values.get("observations") or 0)
            session_totals[name]["signals"] += int(values.get("signals") or 0)
            session_totals[name]["blocks"] += int(values.get("blocks") or 0)
            session_totals[name]["reason_code_counts"].update(values.get("reason_code_counts") or {})
    return public_session_breakdown(session_totals)


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


def session_name(timestamp_utc: Any) -> str:
    try:
        parsed = datetime.fromisoformat(str(timestamp_utc).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "OffHours"
    hour = parsed.hour
    if 0 <= hour < 7:
        return "Asia"
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 21:
        return "NewYork"
    return "OffHours"


def print_summary(report: dict[str, Any]) -> None:
    print("xm-gold-ai-trader dry-run campaign report")
    print(f"campaigns: {report['campaigns_total']}")
    print(f"observations: {report['total_observations']}")
    print(f"unique closed bars: {report['unique_closed_bars']}")
    print(f"duplicate observations: {report['duplicate_observations']}")
    print(f"duplicate skips: {report['duplicate_skip_count']}")
    print(f"signals: {report['signal_count']}")
    print(f"blocks: {report['block_count']}")
    print(f"avg spread: {report['avg_spread']}")
    print(f"max spread: {report['max_spread']}")
    print(f"malformed journals: {report['malformed_journals']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize dry-run observation campaigns.")
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--campaign-dir", default=str(DEFAULT_CAMPAIGN_DIR))
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
