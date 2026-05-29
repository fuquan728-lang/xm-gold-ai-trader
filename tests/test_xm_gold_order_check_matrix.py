from __future__ import annotations

from scripts.order_check_matrix import REASON_NO_ORDER_CHECK_CASE_REACHED, MATRIX_CASES, order_check_matrix
from src.broker.execution_safety import ExecutionConfig, REASON_EMERGENCY_STOP
from src.broker.order_executor import TradingConfig
from tests.test_xm_gold_manual_preflight import FakeManualClient


def test_matrix_never_calls_order_send():
    client = FakeManualClient()

    event = order_check_matrix(client=client, config=TradingConfig())

    assert event["orders_sent"] == 0
    assert client.order_send_calls == []


def test_block_cases_have_reason_codes():
    client = FakeManualClient()
    config = TradingConfig(execution=ExecutionConfig(emergency_stop=True))

    event = order_check_matrix(client=client, config=config)

    assert event["final_decision"] == "BLOCK"
    assert event["reason_codes"] == [REASON_NO_ORDER_CHECK_CASE_REACHED]
    for case in event["cases"]:
        assert case["final_decision"] == "BLOCK"
        assert case["reason_codes"]
        assert REASON_EMERGENCY_STOP in case["reason_codes"]


def test_order_check_only_called_when_local_gates_allow():
    blocked_client = FakeManualClient()
    blocked_config = TradingConfig(execution=ExecutionConfig(emergency_stop=True))

    order_check_matrix(client=blocked_client, config=blocked_config)

    assert blocked_client.order_check_calls == []

    allowed_client = FakeManualClient()
    order_check_matrix(client=allowed_client, config=TradingConfig())

    assert len(allowed_client.order_check_calls) == len(MATRIX_CASES)


def test_orders_sent_always_zero():
    client = FakeManualClient()

    event = order_check_matrix(client=client, config=TradingConfig())

    assert event["orders_sent"] == 0
    assert all(case["candidate_order"] for case in event["cases"])
