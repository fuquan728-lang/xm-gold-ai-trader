from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import scripts.manual_preflight_order_check as manual_preflight
from src.broker.execution_safety import ExecutionConfig, REASON_EMERGENCY_STOP
from src.broker.order_executor import TradingConfig
from src.cli_contract import EXIT_CONTROLLED, event_exit_code


SYMBOL_INFO = {
    "name": "GOLD_",
    "description": "GOLD_",
    "path": "Derivatives\\SpotMetals_\\GOLD_",
    "digits": 2,
    "point": 0.01,
    "spread": 50,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "trade_contract_size": 100.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
    "trade_freeze_level": 0,
    "trade_mode": 4,
}


def account_raw(**overrides):
    data = {
        "login": 123,
        "server": "XM demo",
        "trade_mode": 0,
        "trade_allowed": True,
        "trade_expert": True,
        "balance": 10_000.0,
        "equity": 10_000.0,
        "currency": "USD",
    }
    data.update(overrides)
    return data


class FakeManualClient:
    def __init__(self, *, account=None, positions=None, order_check_retcode=0) -> None:
        self.account = account or account_raw()
        self.positions = positions or []
        self.order_check_retcode = order_check_retcode
        self.order_check_calls: list[dict] = []
        self.order_send_calls: list[dict] = []

    def ensure_symbol(self, symbol):
        return self.get_symbol_info(symbol)

    def get_symbol_info(self, symbol):
        assert symbol == "GOLD_"
        return SimpleNamespace(point=0.01, digits=2, raw=dict(SYMBOL_INFO), filling_mode=2)

    def get_account_info(self):
        return SimpleNamespace(balance=self.account["balance"], equity=self.account["equity"], raw=dict(self.account))

    def get_symbol_tick(self, symbol):
        assert symbol == "GOLD_"
        return SimpleNamespace(bid=2400.0, ask=2400.5, raw={"bid": 2400.0, "ask": 2400.5, "time": 1})

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

    def copy_rates_from_pos(self, symbol, timeframe, count, start_pos=0):
        assert symbol == "GOLD_"
        return []

    def build_market_order_request(self, **kwargs):
        return dict(kwargs)

    def order_check(self, request):
        self.order_check_calls.append(request)
        return SimpleNamespace(retcode=self.order_check_retcode, comment="ok")

    def order_send_checked(self, request, order_check_result, **kwargs):
        self.order_send_calls.append({"request": request, "order_check_result": order_check_result})
        raise AssertionError("manual preflight must never call order_send_checked")


def run_manual(client: FakeManualClient, *, side: str = "BUY", config: TradingConfig | None = None):
    return manual_preflight.manual_preflight_order_check(
        client=client,
        config=config or TradingConfig(),
        side=side,
        stop_points=100.0,
        tp_rr=1.5,
    )


def test_buy_creates_sl_below_entry_and_tp_above_entry():
    client = FakeManualClient()

    event = run_manual(client, side="BUY")

    candidate = event["candidate_order"]
    assert candidate["stop_loss"] < candidate["entry_price"]
    assert candidate["take_profit"] > candidate["entry_price"]


def test_sell_creates_sl_above_entry_and_tp_below_entry():
    client = FakeManualClient()

    event = run_manual(client, side="SELL")

    candidate = event["candidate_order"]
    assert candidate["stop_loss"] > candidate["entry_price"]
    assert candidate["take_profit"] < candidate["entry_price"]


def test_invalid_side_exits_two(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["manual_preflight_order_check.py", "--side", "HOLD"])

    with pytest.raises(SystemExit) as exc:
        manual_preflight.parse_args()

    assert exc.value.code == 2


def test_local_block_does_not_call_order_check():
    client = FakeManualClient()
    config = TradingConfig(execution=ExecutionConfig(emergency_stop=True))

    event = run_manual(client, config=config)

    assert event["final_decision"] == "BLOCK"
    assert REASON_EMERGENCY_STOP in event["reason_codes"]
    assert client.order_check_calls == []


def test_order_check_is_called_only_after_local_gates_allow():
    client = FakeManualClient()

    event = run_manual(client)

    assert event["final_decision"] == "ALLOW"
    assert len(client.order_check_calls) == 1
    assert len(client.order_check_calls[0]["comment"]) <= 31


def test_order_send_is_never_called():
    client = FakeManualClient()

    event = run_manual(client)

    assert event["orders_sent"] == 0
    assert client.order_send_calls == []


def test_block_has_reason_codes():
    client = FakeManualClient()
    config = TradingConfig(execution=ExecutionConfig(emergency_stop=True))

    event = run_manual(client, config=config)

    assert event["final_decision"] == "BLOCK"
    assert event["reason_codes"]


def test_controlled_block_exits_zero():
    client = FakeManualClient()
    config = TradingConfig(execution=ExecutionConfig(emergency_stop=True))
    event = run_manual(client, config=config)

    assert event_exit_code(event) == EXIT_CONTROLLED


def test_main_controlled_block_returns_zero(monkeypatch):
    client = FakeManualClient()

    class ClientContext:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return client

        def __exit__(self, *_args) -> bool:
            return False

    args = SimpleNamespace(
        config="configs/xm_gold_ai_trader.demo.yaml",
        symbol=None,
        side="BUY",
        risk_pct=None,
        stop_points=100.0,
        tp_rr=1.5,
        terminal_path=None,
        login=None,
        password=None,
        server=None,
        timeout_ms=60_000,
        json=True,
    )
    monkeypatch.setattr(manual_preflight, "parse_args", lambda: args)
    monkeypatch.setattr(
        manual_preflight,
        "load_or_default_config",
        lambda _path: TradingConfig(execution=ExecutionConfig(emergency_stop=True)),
    )
    monkeypatch.setattr(manual_preflight, "MT5Client", ClientContext)

    assert manual_preflight.main() == EXIT_CONTROLLED
    assert client.order_check_calls == []
