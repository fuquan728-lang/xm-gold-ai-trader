from __future__ import annotations

from types import SimpleNamespace

from src.broker.execution_safety import ExecutionConfig, REASON_MAX_POSITIONS
from src.broker.order_executor import (
    REASON_ORDER_SEND_DISABLED,
    OrderExecutor,
    TradingConfig,
)
from src.strategy.baseline_signal import TradeSignal


SYMBOL_INFO_FIXTURE = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "trade_contract_size": 100.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
    "spread": 50,
}


class FakeMT5Client:
    def __init__(self, positions=None) -> None:
        self.place_market_order_calls: list[dict] = []
        self.order_check_calls: list[dict] = []
        self.order_send_checked_calls: list[dict] = []
        self.positions = positions or []

    def get_symbol_info(self, symbol: str):
        assert symbol == "GOLD_"
        return SimpleNamespace(point=0.01, raw=dict(SYMBOL_INFO_FIXTURE), filling_mode=2)

    def get_symbol_tick(self, symbol: str):
        assert symbol == "GOLD_"
        return SimpleNamespace(bid=2400.00, ask=2400.50, raw={"bid": 2400.00, "ask": 2400.50})

    def get_account_info(self):
        return SimpleNamespace(
            balance=10_000.0,
            equity=10_000.0,
            raw={
                "balance": 10_000.0,
                "equity": 10_000.0,
                "trade_mode": 0,
                "trade_allowed": True,
                "trade_expert": True,
            },
        )

    def get_open_positions(self, symbol: str):
        assert symbol == "GOLD_"
        return self.positions

    def get_daily_realized_pnl(self, symbol: str):
        assert symbol == "GOLD_"
        return 0.0

    def place_market_order(self, **kwargs):
        self.place_market_order_calls.append(kwargs)
        return SimpleNamespace(retcode=10009, order=123456)

    def build_market_order_request(self, **kwargs):
        return dict(kwargs)

    def order_check(self, request):
        self.order_check_calls.append(request)
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send_checked(self, request, order_check_result):
        self.order_send_checked_calls.append({"request": request, "order_check_result": order_check_result})
        return SimpleNamespace(retcode=10009, order=123456)


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


def test_order_executor_defaults_to_paper_and_does_not_send_live_order():
    client = FakeMT5Client()
    result = OrderExecutor(client).execute_signal(actionable_signal())

    assert result.status == "paper"
    assert result.paper_mode
    assert result.volume > 0
    assert result.reason_codes == (REASON_ORDER_SEND_DISABLED,)
    assert client.place_market_order_calls == []
    assert client.order_check_calls == []
    assert client.order_send_checked_calls == []


def test_order_executor_sends_only_when_allow_order_send_is_explicit_true_with_fake_client():
    client = FakeMT5Client()
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True))
    result = OrderExecutor(client, config).execute_signal(actionable_signal())

    assert result.status == "sent"
    assert not result.paper_mode
    assert client.place_market_order_calls == []
    assert len(client.order_check_calls) == 1
    assert len(client.order_send_checked_calls) == 1
    assert client.order_send_checked_calls[0]["request"]["symbol"] == "GOLD_"


def test_order_executor_blocks_when_existing_gold_position_is_open():
    client = FakeMT5Client(positions=[SimpleNamespace(symbol="GOLD_", volume=0.01, magic=26052601)])
    result = OrderExecutor(client).execute_signal(actionable_signal())

    assert result.status == "blocked"
    assert REASON_MAX_POSITIONS in result.reason_codes
    assert client.place_market_order_calls == []
