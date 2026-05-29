from __future__ import annotations

from src.broker.order_executor import TradingConfig


def test_order_send_defaults_to_disabled():
    config = TradingConfig()

    assert not config.execution.allow_order_send
    assert config.paper_mode


def test_allow_order_send_requires_explicit_execution_flag():
    assert TradingConfig.from_mapping({"execution": {"allow_order_send": False}}).paper_mode
    assert not TradingConfig.from_mapping({"execution": {"allow_order_send": True}}).paper_mode
