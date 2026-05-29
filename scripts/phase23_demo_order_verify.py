from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIRMATION_CODE = "DEMO_ORDER_CONFIRMATION_MISSING"


def main() -> int:
    args = parse_args()
    command = [
        sys.executable,
        "scripts/manual_demo_micro_order.py",
        "--side",
        args.side,
        "--stop-points",
        str(args.stop_points),
        "--tp-rr",
        str(args.tp_rr),
        "--config",
        args.config,
        "--json",
    ]
    if args.confirm_demo_order:
        command.append("--confirm-demo-order")

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    failures: list[str] = []
    if completed.returncode == 2:
        failures.append("manual demo order script returned argparse exit code 2")
    elif completed.returncode != 0:
        failures.append(f"manual demo order script returned {completed.returncode}")

    payload: dict[str, Any] | None = None
    try:
        payload = parse_json_object(completed.stdout)
    except ValueError as exc:
        failures.append(str(exc))

    if payload is not None:
        failures.extend(validate_payload(payload, confirmed=args.confirm_demo_order))

    summary = {
        "project": "xm-gold-ai-trader",
        "phase": "phase23_demo_order_verify",
        "confirmed": args.confirm_demo_order,
        "env_confirmed": os.getenv("XM_GOLD_CONFIRM_DEMO_ORDER") == "YES",
        "passed": not failures,
        "failures": failures,
        "manual_demo_order": {
            "returncode": completed.returncode,
            "final_decision": payload.get("final_decision") if payload else None,
            "reason_codes": payload.get("reason_codes") if payload else None,
            "orders_sent": payload.get("orders_sent") if payload else None,
            "journal_path": payload.get("journal_path") if payload else None,
        },
    }
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0 if not failures else 1


def validate_payload(payload: dict[str, Any], *, confirmed: bool) -> list[str]:
    failures: list[str] = []
    if payload.get("mode") != "manual_demo_micro_order":
        failures.append(f"unexpected mode: {payload.get('mode')!r}")
    orders_sent = int(payload.get("orders_sent") or 0)
    if orders_sent > 1:
        failures.append(f"orders_sent must be <= 1, got {orders_sent}")
    if not confirmed:
        if orders_sent != 0:
            failures.append(f"dry validation must not send orders, got {orders_sent}")
        if payload.get("final_decision") != "BLOCK":
            failures.append("dry validation must controlled-BLOCK without confirmation")
        if CONFIRMATION_CODE not in (payload.get("reason_codes") or []):
            failures.append(f"dry validation must include {CONFIRMATION_CODE}")
    if payload.get("final_decision") == "BLOCK" and not payload.get("reason_codes"):
        failures.append("BLOCK decision must include reason_codes")
    execution = payload.get("config", {}).get("execution", {})
    if confirmed and execution.get("allow_order_send") is not True:
        failures.append("confirmed demo order verification requires execution.allow_order_send true")
    return failures


def parse_json_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(output):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"no JSON object found in stdout: {output[:500]!r}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Phase 2.3 demo order flow; dry by default.")
    parser.add_argument("--side", default="BUY", choices=("BUY", "SELL"))
    parser.add_argument("--stop-points", type=float, default=100.0)
    parser.add_argument("--tp-rr", type=float, default=1.5)
    parser.add_argument("--config", default="config/xm_gold_ai_trader.demo_order_once.yaml")
    parser.add_argument("--confirm-demo-order", action="store_true")
    parser.add_argument("--json", action="store_true", help="Accepted for compatibility; output is always JSON.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
