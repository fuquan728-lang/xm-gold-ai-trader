from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

import scripts.demo_micro_order as demo_micro_order
import scripts.phase2_verify as phase2_verify
import scripts.smoke_check as smoke_check
from src.broker.mt5_client import MT5ClientError
from src.cli_contract import EXIT_CONTROLLED, EXIT_RUNTIME_FAILURE, event_exit_code


def test_controlled_block_exit_code_is_zero():
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "demo_micro_order",
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": ["ALLOW_ORDER_SEND_FALSE"],
    }

    assert event_exit_code(payload) == EXIT_CONTROLLED


def test_block_without_reason_codes_is_runtime_failure_exit_code():
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "demo_micro_order",
        "orders_sent": 0,
        "final_decision": "BLOCK",
        "reason_codes": [],
    }

    assert event_exit_code(payload) == EXIT_RUNTIME_FAILURE


def test_argparse_invalid_argument_exits_two(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["demo_micro_order.py", "--timeframe", "BAD"])

    with pytest.raises(SystemExit) as exc:
        demo_micro_order.parse_args()

    assert exc.value.code == 2


def test_mt5_connection_failure_exits_one(monkeypatch):
    class FailingClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            raise MT5ClientError("connection failed")

        def __exit__(self, *_args) -> bool:
            return False

    args = SimpleNamespace(
        config="configs/xm_gold_ai_trader.demo.yaml",
        symbol=None,
        terminal_path=None,
        login=None,
        password=None,
        server=None,
        timeout_ms=60_000,
        json=True,
    )
    monkeypatch.setattr(smoke_check, "parse_args", lambda: args)
    monkeypatch.setattr(smoke_check, "MT5Client", FailingClient)

    assert smoke_check.main() == EXIT_RUNTIME_FAILURE


def test_phase2_verify_rejects_code_two_from_trading_script(monkeypatch):
    stdout = json.dumps(
        {
            "project": "xm-gold-ai-trader",
            "mode": "demo_micro_order",
            "orders_sent": 0,
            "final_decision": "BLOCK",
            "reason_codes": ["ALLOW_ORDER_SEND_FALSE"],
            "config": {"execution": {"allow_order_send": False}},
        }
    )
    completed = subprocess.CompletedProcess(args=["python", "script"], returncode=2, stdout=stdout, stderr="")
    monkeypatch.setattr(phase2_verify, "run_command", lambda _command: completed)

    result = phase2_verify.run_json_script("demo_micro_order", ["python", "scripts/demo_micro_order.py", "--json"])

    assert not result.passed
    assert result.returncode == 2
    assert "exit code 2" in result.details
