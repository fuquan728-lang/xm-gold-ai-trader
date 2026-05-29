from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cli_contract import validate_event_payload


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    returncode: int
    details: str
    payload: dict[str, Any] | None = None


def main() -> int:
    results: list[CheckResult] = []
    results.append(run_pytest())
    results.append(run_json_script("smoke_check", [sys.executable, "scripts/smoke_check.py", "--json"]))
    results.append(run_json_script("dry_run_signal", [sys.executable, "scripts/dry_run_signal.py", "--json"]))
    results.append(run_json_script("demo_micro_order", [sys.executable, "scripts/demo_micro_order.py", "--json"]))

    preflight = ROOT / "scripts" / "preflight_order_check.py"
    if preflight.exists():
        results.append(
            run_json_script(
                "preflight_order_check",
                [sys.executable, "scripts/preflight_order_check.py", "--json"],
            )
        )

    manual_preflight = ROOT / "scripts" / "manual_preflight_order_check.py"
    if manual_preflight.exists():
        results.append(
            run_json_script(
                "manual_preflight_order_check_buy",
                [sys.executable, "scripts/manual_preflight_order_check.py", "--side", "BUY", "--json"],
            )
        )
        results.append(
            run_json_script(
                "manual_preflight_order_check_sell",
                [sys.executable, "scripts/manual_preflight_order_check.py", "--side", "SELL", "--json"],
            )
        )

    matrix = ROOT / "scripts" / "order_check_matrix.py"
    if matrix.exists():
        results.append(
            run_json_script(
                "order_check_matrix",
                [sys.executable, "scripts/order_check_matrix.py", "--json"],
            )
        )

    print(json.dumps(summary(results), indent=2, sort_keys=True, default=str))
    return 0 if all(result.passed for result in results) else 1


def run_pytest() -> CheckResult:
    completed = run_command([sys.executable, "-m", "pytest"])
    passed = completed.returncode == 0
    details = "pytest passed" if passed else trim_output(completed.stdout, completed.stderr)
    return CheckResult("pytest", passed, completed.returncode, details)


def run_json_script(name: str, command: list[str]) -> CheckResult:
    completed = run_command(command)
    failures: list[str] = []
    if completed.returncode == 2:
        failures.append("script returned exit code 2, reserved for argparse usage errors")
    elif completed.returncode != 0:
        failures.append(f"script returned runtime failure exit code {completed.returncode}")

    try:
        payload = parse_json_object(completed.stdout)
    except ValueError as exc:
        failures.append(str(exc))
        if completed.stderr.strip():
            failures.append(trim_output("", completed.stderr))
        return CheckResult(name, False, completed.returncode, "; ".join(failures), None)

    failures.extend(validate_payload(name, payload))
    passed = not failures
    details = "ok" if passed else "; ".join(failures)
    return CheckResult(name, passed, completed.returncode, details, payload)


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


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


def validate_payload(name: str, payload: dict[str, Any]) -> list[str]:
    failures: list[str] = validate_event_payload(payload)

    if payload.get("orders_sent") != 0:
        failures.append(f"orders_sent must be 0, got {payload.get('orders_sent')!r}")

    if name == "smoke_check" and payload.get("status") != "OK":
        failures.append(f"smoke_check status must be OK, got {payload.get('status')!r}")

    if payload.get("final_decision") == "BLOCK" and not payload.get("reason_codes"):
        failures.append("BLOCK decision must include non-empty reason_codes")

    for index, case in enumerate(payload.get("cases", ())):
        if not isinstance(case, dict):
            failures.append(f"case {index} must be a JSON object")
            continue
        if case.get("final_decision") == "BLOCK" and not case.get("reason_codes"):
            failures.append(f"case {index} BLOCK decision must include non-empty reason_codes")

    execution = payload.get("config", {}).get("execution", {})
    if execution.get("allow_order_send") is not False:
        failures.append("execution.allow_order_send must remain false during phase2 verification")

    return failures


def summary(results: list[CheckResult]) -> dict[str, Any]:
    return {
        "project": "xm-gold-ai-trader",
        "phase": "phase2_verify",
        "passed": all(result.passed for result in results),
        "checks": [
            {
                "name": result.name,
                "passed": result.passed,
                "returncode": result.returncode,
                "details": result.details,
                "final_decision": result.payload.get("final_decision") if result.payload else None,
                "reason_codes": result.payload.get("reason_codes") if result.payload else None,
                "orders_sent": result.payload.get("orders_sent") if result.payload else None,
                "status": result.payload.get("status") if result.payload else None,
            }
            for result in results
        ],
    }


def trim_output(stdout: str, stderr: str) -> str:
    combined = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
    return combined[-2000:] if combined else "command failed without output"


if __name__ == "__main__":
    raise SystemExit(main())
