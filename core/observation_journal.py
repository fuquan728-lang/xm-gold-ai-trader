#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M5 formal observation journal for the v0.25.8 campaign."""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.logger import logger


PROJECT = "xm-gold-ai-trader"
MODE = "m5_formal_observation"
CAMPAIGN_VERSION = "v0.25.8"
JOURNAL_SCHEMA_VERSION = 1
DEFAULT_JOURNAL_DIR = Path("logs/m5_observations")

PERIOD_TO_TIMEFRAME = {
    "1": "M1",
    "2": "M2",
    "3": "M3",
    "4": "M4",
    "5": "M5",
    "6": "M6",
    "10": "M10",
    "12": "M12",
    "15": "M15",
    "20": "M20",
    "30": "M30",
    "16385": "H1",
    "16386": "H2",
    "16387": "H3",
    "16388": "H4",
    "16390": "H6",
    "16392": "H8",
    "16396": "H12",
    "16408": "D1",
    "32769": "W1",
    "49153": "MN1",
}

REQUIRED_OBSERVATION_FIELDS = (
    "request_id",
    "symbol",
    "timeframe",
    "bid",
    "ask",
    "spread_pips",
    "rsi",
    "macd_main",
    "macd_signal",
    "ema50",
    "ai_action_raw",
    "ai_action_final",
    "confidence",
    "blocked_by",
    "response_matched",
    "stale_response",
    "latency_ms",
    "trade_executed",
)


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_action(value: Any) -> str:
    action = str(value or "HOLD").upper()
    return action if action in {"BUY", "SELL", "HOLD"} else "HOLD"


def derive_timeframe(request_data: Mapping[str, Any], response_data: Mapping[str, Any]) -> str | None:
    explicit = request_data.get("timeframe") or response_data.get("timeframe")
    if explicit:
        text = str(explicit).upper()
        return text.replace("PERIOD_", "")

    request_id = str(response_data.get("request_id") or request_data.get("request_id") or "")
    parts = request_id.rsplit("_", 3)
    if len(parts) == 4 and parts[1] in PERIOD_TO_TIMEFRAME:
        return PERIOD_TO_TIMEFRAME[parts[1]]

    match = re.search(r"_([0-9]+)_\d{9,}_\d+$", request_id)
    if match:
        return PERIOD_TO_TIMEFRAME.get(match.group(1))
    return None


def raw_action_from_response(response_data: Mapping[str, Any]) -> str:
    validation = response_data.get("indicator_validation")
    if isinstance(validation, Mapping):
        original = validation.get("original_action")
        if original:
            return normalize_action(original)
    return normalize_action(response_data.get("original_action") or response_data.get("action"))


def spread_pips_from_payload(request_data: Mapping[str, Any], response_data: Mapping[str, Any]) -> float | None:
    validation = response_data.get("indicator_validation")
    if isinstance(validation, Mapping):
        spread_pips = safe_float(validation.get("spread_pips"))
        if spread_pips is not None:
            return spread_pips

    bid = safe_float(request_data.get("bid"))
    ask = safe_float(request_data.get("ask"))
    if bid is not None and ask is not None and ask >= bid:
        symbol = str(request_data.get("symbol") or response_data.get("symbol") or "")
        pip_size = 0.10 if "GOLD" in symbol.upper() or symbol.upper().startswith("XAU") else 0.0001
        return (ask - bid) / pip_size if pip_size > 0 else None
    return safe_float(request_data.get("spread"))


def build_observation(
    request_data: Mapping[str, Any],
    response_data: Mapping[str, Any],
    *,
    response_write_ok: bool = True,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    blocked_by = response_data.get("blocked_by")
    if not isinstance(blocked_by, list):
        blocked_by = []

    latency_ms = safe_float(response_data.get("latency_total_ms"))
    if latency_ms is None:
        latency_ms = safe_float(response_data.get("latency_ai_ms"))
    ea_timeout_seconds = safe_float(response_data.get("ea_timeout_seconds") or request_data.get("ea_timeout_seconds"))
    timeout = bool(
        latency_ms is not None
        and ea_timeout_seconds is not None
        and latency_ms > ea_timeout_seconds * 1000
    )

    return {
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "project": PROJECT,
        "mode": MODE,
        "campaign_version": CAMPAIGN_VERSION,
        "timestamp": recorded_at or datetime.now().isoformat(),
        "request_id": str(response_data.get("request_id") or request_data.get("request_id") or ""),
        "protocol_version": response_data.get("protocol_version"),
        "symbol": str(request_data.get("symbol") or response_data.get("symbol") or "UNKNOWN"),
        "timeframe": derive_timeframe(request_data, response_data),
        "bid": safe_float(request_data.get("bid")),
        "ask": safe_float(request_data.get("ask")),
        "spread_pips": spread_pips_from_payload(request_data, response_data),
        "rsi": safe_float(request_data.get("rsi")),
        "macd_main": safe_float(request_data.get("macd_main")),
        "macd_signal": safe_float(request_data.get("macd_signal")),
        "ema50": safe_float(request_data.get("ema50")),
        "ai_action_raw": raw_action_from_response(response_data),
        "ai_action_final": normalize_action(response_data.get("action")),
        "confidence": safe_float(response_data.get("confidence")),
        "blocked_by": blocked_by,
        "response_matched": bool(response_data.get("response_matched")),
        "stale_response": bool(response_data.get("stale_response")),
        "latency_ms": int(latency_ms) if latency_ms is not None else None,
        "latency_ai_ms": response_data.get("latency_ai_ms"),
        "ea_timeout_seconds": ea_timeout_seconds,
        "timeout": timeout,
        "trade_executed": False,
        "response_write_ok": bool(response_write_ok),
        "use_deepseek": bool(response_data.get("use_deepseek")),
        "cached": bool(response_data.get("cached")),
        "reason": response_data.get("reason", ""),
    }


class M5ObservationJournal:
    def __init__(self, journal_dir: str | Path = DEFAULT_JOURNAL_DIR):
        self.journal_dir = Path(journal_dir)
        self._lock = threading.Lock()

    def record(
        self,
        request_data: Mapping[str, Any],
        response_data: Mapping[str, Any],
        *,
        response_write_ok: bool = True,
    ) -> Path:
        observation = build_observation(
            request_data,
            response_data,
            response_write_ok=response_write_ok,
        )
        date_text = observation["timestamp"][:10].replace("-", "")
        path = self.journal_dir / f"{date_text}.jsonl"
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(observation, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        logger.info(
            "[OBS] journaled request_id=%s timeframe=%s final=%s blocked_by=%s",
            observation["request_id"],
            observation["timeframe"],
            observation["ai_action_final"],
            observation["blocked_by"],
        )
        return path


def iter_observations(journal_dir: str | Path = DEFAULT_JOURNAL_DIR) -> Iterable[dict[str, Any]]:
    root = Path(journal_dir)
    if not root.exists():
        return []

    observations: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                observations.append(
                    {"_malformed": True, "path": str(path), "line": line_no, "error": str(exc)}
                )
                continue
            if isinstance(payload, dict):
                observations.append(payload)
            else:
                observations.append(
                    {"_malformed": True, "path": str(path), "line": line_no, "error": "JSON root is not an object"}
                )
    return observations


def summarize_observations(
    observations: Iterable[Mapping[str, Any]],
    *,
    symbol: str | None = "GOLD_",
    timeframe: str | None = "M5",
    target: int = 30,
) -> dict[str, Any]:
    rows = [dict(row) for row in observations]
    malformed = [row for row in rows if row.get("_malformed")]
    valid = [row for row in rows if not row.get("_malformed")]
    if symbol:
        valid = [row for row in valid if row.get("symbol") == symbol]
    if timeframe:
        valid = [row for row in valid if row.get("timeframe") == timeframe]

    raw_counter: Counter[str] = Counter(normalize_action(row.get("ai_action_raw")) for row in valid)
    final_counter: Counter[str] = Counter(normalize_action(row.get("ai_action_final")) for row in valid)
    block_counter: Counter[str] = Counter()
    missing_required_count = 0
    for row in valid:
        missing = [field for field in REQUIRED_OBSERVATION_FIELDS if field not in row]
        if missing:
            missing_required_count += 1
        for block in row.get("blocked_by") or []:
            block_counter[str(block)] += 1

    total = len(valid)
    matched = sum(1 for row in valid if row.get("response_matched") is True)
    stale = sum(1 for row in valid if row.get("stale_response") is True)
    timeouts = sum(1 for row in valid if row.get("timeout") is True)
    trades = sum(1 for row in valid if row.get("trade_executed") is True)
    latencies = [safe_float(row.get("latency_ms")) for row in valid]
    latencies = [value for value in latencies if value is not None]

    return {
        "project": PROJECT,
        "mode": "m5_observation_report",
        "campaign_version": CAMPAIGN_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "target": target,
        "total_requests": total,
        "matched_responses": matched,
        "stale_responses_ignored": stale,
        "timeouts": timeouts,
        "ai_action_raw_BUY": raw_counter["BUY"],
        "ai_action_raw_SELL": raw_counter["SELL"],
        "ai_action_raw_HOLD": raw_counter["HOLD"],
        "final_action_BUY": final_counter["BUY"],
        "final_action_SELL": final_counter["SELL"],
        "final_action_HOLD": final_counter["HOLD"],
        "blocked_by_ACTION_HOLD": block_counter["ACTION_HOLD"],
        "blocked_by_LOW_CONFIDENCE": block_counter["LOW_CONFIDENCE"],
        "blocked_by_SPREAD_TOO_HIGH": block_counter["SPREAD_TOO_HIGH"],
        "blocked_by_SAFETY_GATE": block_counter["SAFETY_GATE"],
        "blocked_by_counts": dict(sorted(block_counter.items())),
        "trades_executed": trades,
        "malformed_journals": len(malformed),
        "missing_required_field_journals": missing_required_count,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "checkpoint_pass": (
            total >= target
            and matched == total
            and stale == 0
            and timeouts == 0
            and trades == 0
            and not malformed
            and missing_required_count == 0
        ),
    }


_global_journal: M5ObservationJournal | None = None


def get_m5_observation_journal(journal_dir: str | Path = DEFAULT_JOURNAL_DIR) -> M5ObservationJournal:
    global _global_journal
    if _global_journal is None:
        _global_journal = M5ObservationJournal(journal_dir)
    return _global_journal
