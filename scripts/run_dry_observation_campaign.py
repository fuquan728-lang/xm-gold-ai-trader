from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_dry_run_signal_journal import DEFAULT_JOURNAL_DIR, DEFAULT_PARAMETER_REPORT, PROJECT, observe_once
from src.broker.mt5_client import MT5Client, MT5ConnectionConfig
from src.logging_config import configure_logging


MODE = "dry_observation_campaign"
DEFAULT_CAMPAIGN_DIR = Path("logs/dry_run_campaigns")


def main() -> int:
    args = parse_args()
    logger = configure_logging(logger_name="run_dry_observation_campaign")
    try:
        metadata = run_campaign(args)
    except Exception as exc:  # pragma: no cover - defensive CLI guard.
        logger.exception("dry observation campaign failed")
        print(str(exc), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(metadata, indent=2, sort_keys=True, default=str))
    else:
        print_summary(metadata)
    return 0


def run_campaign(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[MT5ConnectionConfig], Any] = MT5Client,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] | None = None,
    emergency_stop_path: Path | None = None,
) -> dict[str, Any]:
    if args.max_iterations <= 0:
        raise ValueError("--max-iterations must be positive")
    campaign_id = args.campaign_id or new_campaign_id()
    campaign_dir = Path(args.campaign_dir)
    journal_dir = Path(args.journal_dir)
    now_func = now or (lambda: datetime.now(timezone.utc))
    started = now_func()
    errors: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for index in range(1, args.max_iterations + 1):
        observation_args = build_observation_args(args, campaign_id)
        try:
            event = observe_once(
                observation_args,
                client_factory=client_factory,
                journal_dir=journal_dir,
                emergency_stop_path=emergency_stop_path,
            )
            if int(event.get("orders_sent") or 0) != 0:
                errors.append(
                    {
                        "iteration": index,
                        "reason_code": "ORDERS_SENT_NONZERO",
                        "message": f"observation reported orders_sent={event.get('orders_sent')!r}",
                    }
                )
            observations.append(event)
        except Exception as exc:
            errors.append({"iteration": index, "reason_code": "OBSERVATION_FAILED", "message": str(exc)})
        if index < args.max_iterations:
            sleep(float(args.interval_seconds))

    ended = now_func()
    metadata = {
        "project": PROJECT,
        "mode": MODE,
        "campaign_id": campaign_id,
        "started_at_utc": started.isoformat(),
        "ended_at_utc": ended.isoformat(),
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "interval_seconds": float(args.interval_seconds),
        "max_iterations": args.max_iterations,
        "bar_close_only": bool(getattr(args, "bar_close_only", False)),
        "total_poll_iterations": args.max_iterations,
        "total_iterations": args.max_iterations,
        "journal_count": len([event for event in observations if event.get("journal_path")]),
        "journal_paths": [event.get("journal_path") for event in observations if event.get("journal_path")],
        "unique_closed_bars": unique_closed_bar_count(observations),
        "duplicate_bar_skipped": sum(1 for event in observations if event.get("final_decision") == "SKIP"),
        "signal_count": sum(1 for event in observations if event.get("final_decision") == "SIGNAL"),
        "block_count": sum(1 for event in observations if event.get("final_decision") == "BLOCK"),
        "skip_count": sum(1 for event in observations if event.get("final_decision") == "SKIP"),
        "errors": errors,
        "orders_sent": 0,
        "observed_orders_sent_sum": sum(int(event.get("orders_sent") or 0) for event in observations),
        "hard_safety": {
            "ai_model_trading": False,
            "order_check": False,
            "order_send": False,
            "martingale": False,
            "grid": False,
            "lot_increase_after_loss": False,
        },
    }
    campaign_dir.mkdir(parents=True, exist_ok=True)
    path = campaign_dir / f"{campaign_id}.json"
    metadata["campaign_path"] = str(path)
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return metadata


def build_observation_args(args: argparse.Namespace, campaign_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        config=args.config,
        symbol=args.symbol,
        timeframe=args.timeframe,
        bars=args.bars,
        start_pos=args.start_pos,
        parameter_report=args.parameter_report,
        journal_dir=args.journal_dir,
        campaign_id=campaign_id,
        fallback_fast_sma=args.fallback_fast_sma,
        fallback_slow_sma=args.fallback_slow_sma,
        atr_period=args.atr_period,
        fallback_atr_stop_multiplier=args.fallback_atr_stop_multiplier,
        fallback_reward_risk_ratio=args.fallback_reward_risk_ratio,
        once=True,
        loop=False,
        interval_seconds=args.interval_seconds,
        max_iterations=1,
        terminal_path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
        timeout_ms=args.timeout_ms,
        json=args.json,
        bar_close_only=bool(getattr(args, "bar_close_only", False)),
    )


def unique_closed_bar_count(observations: list[dict[str, Any]]) -> int:
    return len(
        {
            event.get("latest_closed_bar_time")
            for event in observations
            if event.get("journal_path") and event.get("latest_closed_bar_time")
        }
    )


def new_campaign_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"dryrun_{timestamp}_{uuid4().hex[:8]}"


def print_summary(metadata: dict[str, Any]) -> None:
    print("xm-gold-ai-trader dry observation campaign")
    print(f"campaign_id: {metadata['campaign_id']}")
    print(f"iterations: {metadata['total_iterations']}")
    print(f"journals: {metadata['journal_count']}")
    print(f"unique closed bars: {metadata['unique_closed_bars']}")
    print(f"duplicate bar skipped: {metadata['duplicate_bar_skipped']}")
    print(f"signals: {metadata['signal_count']}")
    print(f"blocks: {metadata['block_count']}")
    print(f"errors: {len(metadata['errors'])}")
    print(f"campaign_path: {metadata['campaign_path']}")
    print("orders_sent: 0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded dry-run GOLD_ observation campaign.")
    parser.add_argument("--config", default="configs/xm_gold_ai_trader.demo.yaml")
    parser.add_argument("--symbol", default=os.getenv("XM_GOLD_SYMBOL", "GOLD_"))
    parser.add_argument("--timeframe", default="M15", choices=("M1", "M5", "M15", "M30", "H1", "H4", "D1"))
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--max-iterations", type=int, required=True)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--campaign-dir", default=str(DEFAULT_CAMPAIGN_DIR))
    parser.add_argument("--journal-dir", default=str(DEFAULT_JOURNAL_DIR))
    parser.add_argument("--bar-close-only", action="store_true")
    parser.add_argument("--bars", type=int, default=250)
    parser.add_argument("--start-pos", type=int, default=1)
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
