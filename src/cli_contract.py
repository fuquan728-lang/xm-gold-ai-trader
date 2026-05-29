from __future__ import annotations

from typing import Any


EXIT_CONTROLLED = 0
EXIT_RUNTIME_FAILURE = 1

CONTROLLED_FINAL_DECISIONS = {"ALLOW", "BLOCK", "SIGNAL", "SKIP", "SENT", "CLOSED", "NO_MATCH"}


def event_exit_code(payload: dict[str, Any]) -> int:
    return EXIT_CONTROLLED if validate_event_payload(payload) == [] else EXIT_RUNTIME_FAILURE


def validate_event_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not isinstance(payload, dict):
        return ["payload is not a JSON object"]

    status = payload.get("status")
    final_decision = payload.get("final_decision")
    if status == "OK":
        if payload.get("orders_sent") != 0:
            failures.append("orders_sent must be 0 for smoke checks")
        return failures

    if final_decision not in CONTROLLED_FINAL_DECISIONS:
        failures.append(f"unknown final_decision/status: {final_decision!r}/{status!r}")
        return failures

    if final_decision == "BLOCK" and not payload.get("reason_codes"):
        failures.append("BLOCK decision must include non-empty reason_codes")

    if "orders_sent" not in payload:
        failures.append("orders_sent is missing")
    else:
        orders_sent = _int_or_none(payload.get("orders_sent"))
        if orders_sent is None:
            failures.append("orders_sent must be an integer")
        elif final_decision in {"ALLOW", "BLOCK", "SIGNAL", "SKIP", "NO_MATCH"} and orders_sent != 0:
            failures.append(f"{final_decision} decision must not send orders")
        elif final_decision in {"SENT", "CLOSED"} and orders_sent < 1:
            failures.append(f"{final_decision} decision must include at least one sent order")

    return failures


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
