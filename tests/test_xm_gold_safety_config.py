from __future__ import annotations

import pytest

from src.broker.order_executor import TradingConfig


def test_order_send_defaults_to_disabled():
    config = TradingConfig()

    assert not config.execution.allow_order_send
    assert config.paper_mode


def test_allow_order_send_requires_explicit_execution_flag():
    assert TradingConfig.from_mapping({"execution": {"allow_order_send": False}}).paper_mode
    assert not TradingConfig.from_mapping({"execution": {"allow_order_send": True}}).paper_mode


def test_allow_order_send_string_false_remains_paper_mode():
    config = TradingConfig.from_mapping({"execution": {"allow_order_send": "false"}})

    assert config.execution.allow_order_send is False
    assert config.paper_mode


def test_boolean_config_rejects_unknown_strings():
    with pytest.raises(ValueError, match="allow_order_send"):
        TradingConfig.from_mapping({"execution": {"allow_order_send": "definitely"}})


def test_risk_boolean_strings_are_normalized_before_validation():
    config = TradingConfig.from_mapping(
        {
            "risk": {
                "one_position_only": "false",
                "allow_martingale": "false",
                "allow_grid": "false",
                "allow_lot_increase_after_loss": "false",
            }
        }
    )

    assert config.risk.one_position_only is False
