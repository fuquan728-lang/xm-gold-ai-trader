from __future__ import annotations

from types import SimpleNamespace

from scripts.close_demo_positions import close_matching_demo_positions
from scripts.demo_micro_order import execute_demo_micro_order
from src.broker.execution_safety import (
    ExecutionConfig,
    REASON_ALLOW_ORDER_SEND_FALSE,
    REASON_ACCOUNT_INFO_UNAVAILABLE,
    REASON_EMERGENCY_STOP,
    REASON_EXISTING_MAGIC_POSITION,
    REASON_EXPERT_TRADING_DISABLED,
    REASON_NON_DEMO_ACCOUNT,
    REASON_ORDER_CHECK_FAILED,
    REASON_ORDER_SEND_FAILED,
    REASON_TRADE_NOT_ALLOWED,
    evaluate_execution_safety,
)
from src.broker.order_executor import TradingConfig
from src.strategy.baseline_signal import TradeSignal


SYMBOL_INFO = {
    "name": "GOLD_",
    "path": "Derivatives\\SpotMetals_\\GOLD_",
    "point": 0.01,
    "spread": 50,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "trade_contract_size": 100.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
}


def account_raw(**overrides):
    data = {
        "login": 123,
        "server": "demo",
        "trade_mode": 0,
        "trade_allowed": True,
        "trade_expert": True,
        "balance": 10_000.0,
        "equity": 10_000.0,
        "currency": "USD",
    }
    data.update(overrides)
    return data


def actionable_signal() -> TradeSignal:
    return TradeSignal(
        symbol="GOLD_",
        side="BUY",
        confidence=0.55,
        entry_price=2400.50,
        stop_loss_price=2399.50,
        take_profit_price=2402.00,
        reason="test signal",
    )


class FakePhase2Client:
    def __init__(self, *, positions=None, account=None, order_check_retcode=0, order_send_retcode=10009):
        self.positions = positions or []
        self.account = account or account_raw()
        self.order_check_retcode = order_check_retcode
        self.order_send_retcode = order_send_retcode
        self.order_check_calls: list[dict] = []
        self.order_send_checked_calls: list[dict] = []

    def get_symbol_info(self, symbol):
        assert symbol == "GOLD_"
        return SimpleNamespace(point=0.01, raw=dict(SYMBOL_INFO), filling_mode=2)

    def get_symbol_tick(self, symbol):
        assert symbol == "GOLD_"
        return SimpleNamespace(bid=2400.0, ask=2400.5, raw={"bid": 2400.0, "ask": 2400.5})

    def get_account_info(self):
        return SimpleNamespace(balance=self.account["balance"], equity=self.account["equity"], raw=dict(self.account))

    def get_open_positions(self, symbol):
        assert symbol == "GOLD_"
        return self.positions

    def get_daily_realized_pnl(self, symbol):
        assert symbol == "GOLD_"
        return 0.0

    def get_daily_order_count(self, symbol, magic_number):
        assert symbol == "GOLD_"
        assert magic_number == 26052601
        return 0

    def build_market_order_request(self, **kwargs):
        return dict(kwargs)

    def build_close_position_request(self, *, position, deviation_points, magic_number, comment):
        return {"symbol": position.symbol, "position": position.ticket, "magic": magic_number, "comment": comment}

    def order_check(self, request):
        self.order_check_calls.append(request)
        return SimpleNamespace(retcode=self.order_check_retcode, comment="check")

    def order_send_checked(self, request, order_check_result, **kwargs):
        self.order_send_checked_calls.append({"request": request, "order_check_result": order_check_result})
        return SimpleNamespace(retcode=self.order_send_retcode, order=999, comment="sent")


def test_emergency_stop_blocks_everything():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(emergency_stop=True),
        account_info=account_raw(),
        symbol="GOLD_",
        require_order_send_permission=True,
    )

    assert not decision.allowed
    assert REASON_EMERGENCY_STOP in decision.reason_codes


def test_account_info_none_blocks():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(),
        account_info=None,
        symbol="GOLD_",
    )

    assert not decision.allowed
    assert REASON_ACCOUNT_INFO_UNAVAILABLE in decision.reason_codes


def test_allow_order_send_false_blocks_order_send():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(allow_order_send=False),
        account_info=account_raw(),
        symbol="GOLD_",
        require_order_send_permission=True,
    )

    assert not decision.allowed
    assert REASON_ALLOW_ORDER_SEND_FALSE in decision.reason_codes


def test_non_demo_account_blocks_when_demo_required():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(require_demo_account=True),
        account_info=account_raw(trade_mode=2),
        symbol="GOLD_",
    )

    assert not decision.allowed
    assert REASON_NON_DEMO_ACCOUNT in decision.reason_codes


def test_trade_allowed_false_blocks():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(),
        account_info=account_raw(trade_allowed=False),
        symbol="GOLD_",
    )

    assert not decision.allowed
    assert REASON_TRADE_NOT_ALLOWED in decision.reason_codes


def test_trade_expert_false_blocks():
    decision = evaluate_execution_safety(
        config=ExecutionConfig(),
        account_info=account_raw(trade_expert=False),
        symbol="GOLD_",
    )

    assert not decision.allowed
    assert REASON_EXPERT_TRADING_DISABLED in decision.reason_codes


def test_order_check_failure_blocks_order_send():
    client = FakePhase2Client(order_check_retcode=10030)
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))

    event = execute_demo_micro_order(client, config, actionable_signal())

    assert event["final_decision"] == "BLOCK"
    assert REASON_ORDER_CHECK_FAILED in event["reason_codes"]
    assert len(client.order_check_calls) == 1
    assert client.order_send_checked_calls == []


def test_order_send_failure_retcode_blocks_demo_micro_order():
    client = FakePhase2Client(order_send_retcode=10030)
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))

    event = execute_demo_micro_order(client, config, actionable_signal())

    assert event["final_decision"] == "BLOCK"
    assert REASON_ORDER_SEND_FAILED in event["reason_codes"]
    assert event["orders_sent"] == 0
    assert len(client.order_send_checked_calls) == 1


def test_existing_magic_position_blocks_new_order():
    position = SimpleNamespace(symbol="GOLD_", magic=26052601, volume=0.01, ticket=1)
    client = FakePhase2Client(positions=[position])
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))

    event = execute_demo_micro_order(client, config, actionable_signal())

    assert event["final_decision"] == "BLOCK"
    assert REASON_EXISTING_MAGIC_POSITION in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_close_demo_positions_only_targets_matching_symbol_and_magic():
    matching = SimpleNamespace(symbol="GOLD_", magic=26052601, volume=0.01, ticket=1)
    wrong_magic = SimpleNamespace(symbol="GOLD_", magic=111, volume=0.01, ticket=2)
    wrong_symbol = SimpleNamespace(symbol="XAUEUR_", magic=26052601, volume=0.01, ticket=3)
    client = FakePhase2Client(positions=[matching, wrong_magic, wrong_symbol])
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))

    event = close_matching_demo_positions(client, config)

    assert event["final_decision"] == "CLOSED"
    assert event["orders_sent"] == 1
    assert len(event["target_positions"]) == 1
    assert event["target_positions"][0]["ticket"] == 1
    assert client.order_send_checked_calls[0]["request"]["position"] == 1


def test_close_demo_positions_failed_order_send_does_not_count_as_closed():
    matching = SimpleNamespace(symbol="GOLD_", magic=26052601, volume=0.01, ticket=1)
    client = FakePhase2Client(positions=[matching], order_send_retcode=10030)
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))

    event = close_matching_demo_positions(client, config)

    assert event["final_decision"] == "BLOCK"
    assert event["orders_sent"] == 0
    assert REASON_ORDER_SEND_FAILED in event["reason_codes"]
    assert event["close_attempts"][0]["sent"] is False
