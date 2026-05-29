from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.close_demo_positions import close_matching_demo_positions
from scripts.manual_demo_micro_order import (
    REASON_DEMO_ORDER_CONFIRMATION_MISSING,
    manual_demo_micro_order,
)
from src.broker.execution_safety import (
    ExecutionConfig,
    REASON_ALLOW_ORDER_SEND_FALSE,
    REASON_DAILY_LOSS_LIMIT_REACHED,
    REASON_EMERGENCY_STOP_FILE_PRESENT,
    REASON_EXISTING_MAGIC_POSITION,
    REASON_NON_DEMO_ACCOUNT,
    REASON_ONE_SHOT_ORDER_ALREADY_USED,
    REASON_ORDER_CHECK_FAILED,
)
from src.broker.order_executor import TradingConfig, load_trading_config
from src.cli_contract import EXIT_CONTROLLED, event_exit_code
from src.runtime.lock import REASON_RUNTIME_LOCK_EXISTS, REASON_STALE_RUNTIME_LOCK_RECOVERED, RuntimeLock
from src.strategy.risk_manager import RiskConfig


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


class FakeDemoOrderClient:
    def __init__(
        self,
        *,
        account=None,
        positions=None,
        post_send_positions=None,
        order_check_retcode=0,
        order_send_retcode=10009,
        history_deals=None,
    ) -> None:
        self.account = account or account_raw()
        self.positions = positions or []
        self.post_send_positions = post_send_positions
        self.order_check_retcode = order_check_retcode
        self.order_send_retcode = order_send_retcode
        self.history_deals = history_deals or []
        self.order_check_calls: list[dict] = []
        self.order_send_checked_calls: list[dict] = []
        self.open_position_calls = 0

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
        self.open_position_calls += 1
        if self.open_position_calls > 1 and self.post_send_positions is not None:
            return self.post_send_positions
        return self.positions

    def get_daily_realized_pnl(self, symbol):
        assert symbol == "GOLD_"
        return 0.0

    def get_daily_order_count(self, symbol, magic_number):
        assert symbol == "GOLD_"
        assert magic_number == 26052601
        return 0

    def get_history_deals(self, date_from, date_to):
        return self.history_deals

    def build_market_order_request(self, **kwargs):
        return dict(kwargs)

    def order_check(self, request):
        self.order_check_calls.append(request)
        return SimpleNamespace(retcode=self.order_check_retcode, comment="check")

    def order_send_checked(self, request, order_check_result):
        self.order_send_checked_calls.append({"request": request, "order_check_result": order_check_result})
        return SimpleNamespace(retcode=self.order_send_retcode, order=999, comment="sent")


def send_config() -> TradingConfig:
    return TradingConfig(execution=ExecutionConfig(allow_order_send=True))


def matching_position():
    return SimpleNamespace(symbol="GOLD_", magic=26052601, volume=0.01, ticket=999)


def write_demo_journal(path: Path, **overrides) -> None:
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "manual_demo_micro_order",
        "journal_schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "final_decision": "SENT",
        "reason_codes": [],
        "orders_sent": 1,
        "orders_accepted": 1,
        "account": {"login": 123, "server": "XM demo"},
        "symbol": {"name": "GOLD_"},
        "config": {"symbol": "GOLD_", "magic_number": 26052601},
        "candidate_order": {"symbol": "GOLD_", "mt5_request": {"magic": 26052601}},
        "order_send_result": {"retcode": 10009, "order": 111, "deal": 222},
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def run_demo(
    client: FakeDemoOrderClient,
    tmp_path: Path,
    *,
    config: TradingConfig | None = None,
    cli=True,
    env=True,
    runtime_lock_path: Path | None = None,
    emergency_stop_path: Path | None = None,
):
    return manual_demo_micro_order(
        client=client,
        config=config or send_config(),
        side="BUY",
        stop_points=100.0,
        tp_rr=1.5,
        cli_confirmed=cli,
        env_confirmed=env,
        journal_dir=tmp_path,
        runtime_lock_path=runtime_lock_path or tmp_path / "runtime.lock",
        emergency_stop_path=emergency_stop_path or tmp_path / "EMERGENCY_STOP",
    )


def test_missing_confirm_demo_order_blocks(tmp_path):
    event = run_demo(FakeDemoOrderClient(), tmp_path, cli=False, env=True)

    assert event["final_decision"] == "BLOCK"
    assert REASON_DEMO_ORDER_CONFIRMATION_MISSING in event["reason_codes"]
    assert event["orders_sent"] == 0
    assert event["side"] == "BUY"
    assert event["block_stage"] == "pre_confirmation"


def test_missing_env_var_blocks(tmp_path):
    event = run_demo(FakeDemoOrderClient(), tmp_path, cli=True, env=False)

    assert event["final_decision"] == "BLOCK"
    assert REASON_DEMO_ORDER_CONFIRMATION_MISSING in event["reason_codes"]
    assert event["orders_sent"] == 0
    assert event["side"] == "BUY"
    assert event["block_stage"] == "pre_confirmation"


def test_allow_order_send_false_blocks(tmp_path):
    client = FakeDemoOrderClient()
    event = run_demo(client, tmp_path, config=TradingConfig())

    assert event["final_decision"] == "BLOCK"
    assert REASON_ALLOW_ORDER_SEND_FALSE in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_non_demo_account_blocks(tmp_path):
    client = FakeDemoOrderClient(account=account_raw(trade_mode=2))

    event = run_demo(client, tmp_path)

    assert event["final_decision"] == "BLOCK"
    assert REASON_NON_DEMO_ACCOUNT in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_existing_magic_position_blocks(tmp_path):
    client = FakeDemoOrderClient(positions=[matching_position()])

    event = run_demo(client, tmp_path)

    assert event["final_decision"] == "BLOCK"
    assert REASON_EXISTING_MAGIC_POSITION in event["reason_codes"]
    assert client.order_check_calls == []
    assert client.order_send_checked_calls == []


def test_order_check_failure_blocks_order_send(tmp_path):
    client = FakeDemoOrderClient(order_check_retcode=10030)

    event = run_demo(client, tmp_path)

    assert event["final_decision"] == "BLOCK"
    assert REASON_ORDER_CHECK_FAILED in event["reason_codes"]
    assert len(client.order_check_calls) == 1
    assert client.order_send_checked_calls == []


def test_order_send_called_exactly_once_when_all_gates_pass(tmp_path):
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path)

    assert event["final_decision"] == "SENT"
    assert event["orders_sent"] == 1
    assert len(client.order_send_checked_calls) == 1
    assert client.order_send_checked_calls[0]["request"]["volume"] == 0.01


def test_position_verification_runs_after_successful_order_send(tmp_path):
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path)

    assert client.open_position_calls >= 2
    assert event["position_verification"]["checked"]
    assert event["position_verification"]["matched"]


def test_journal_is_written(tmp_path):
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path)

    journal_path = Path(event["journal_path"])
    assert journal_path.exists()
    assert journal_path.parent == tmp_path


def test_controlled_block_exits_zero(tmp_path):
    event = run_demo(FakeDemoOrderClient(), tmp_path, config=TradingConfig())

    assert event_exit_code(event) == EXIT_CONTROLLED


def test_runtime_lock_blocks_second_run(tmp_path):
    lock_path = tmp_path / "runtime.lock"
    lock = RuntimeLock(lock_path)
    result = lock.acquire()
    assert result.acquired
    client = FakeDemoOrderClient()

    try:
        event = run_demo(client, tmp_path, runtime_lock_path=lock_path)
    finally:
        lock.release()

    assert event["final_decision"] == "BLOCK"
    assert REASON_RUNTIME_LOCK_EXISTS in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_stale_runtime_lock_recovery_allows_run(tmp_path):
    lock_path = tmp_path / "runtime.lock"
    old_timestamp = datetime.now(timezone.utc) - timedelta(hours=2)
    lock_path.write_text(
        json.dumps({"project": "xm-gold-ai-trader", "token": "old", "acquired_at_utc": old_timestamp.isoformat()}),
        encoding="utf-8",
    )
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path, runtime_lock_path=lock_path)

    assert event["final_decision"] == "SENT"
    assert REASON_STALE_RUNTIME_LOCK_RECOVERED in event["warning_codes"]
    assert not lock_path.exists()


def test_emergency_stop_file_blocks_manual_demo_order(tmp_path):
    emergency_stop = tmp_path / "EMERGENCY_STOP"
    emergency_stop.write_text("stop", encoding="utf-8")
    client = FakeDemoOrderClient()

    event = run_demo(client, tmp_path, emergency_stop_path=emergency_stop)

    assert event["final_decision"] == "BLOCK"
    assert REASON_EMERGENCY_STOP_FILE_PRESENT in event["reason_codes"]
    assert client.order_send_checked_calls == []


class FakeCloseClient(FakeDemoOrderClient):
    def build_close_position_request(self, **kwargs):
        return dict(kwargs)


def test_emergency_stop_file_blocks_close_demo_positions(tmp_path):
    emergency_stop = tmp_path / "EMERGENCY_STOP"
    emergency_stop.write_text("stop", encoding="utf-8")
    client = FakeCloseClient(positions=[matching_position()])

    event = close_matching_demo_positions(client, send_config(), emergency_stop_path=emergency_stop)

    assert event["final_decision"] == "BLOCK"
    assert REASON_EMERGENCY_STOP_FILE_PRESENT in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_one_shot_guard_blocks_after_accepted_order(tmp_path):
    write_demo_journal(tmp_path / "accepted.json")
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True, one_shot_only=True))
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path, config=config)

    assert event["final_decision"] == "BLOCK"
    assert REASON_ONE_SHOT_ORDER_ALREADY_USED in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_rejected_order_send_does_not_count_as_one_shot_used(tmp_path):
    write_demo_journal(
        tmp_path / "rejected.json",
        final_decision="BLOCK",
        reason_codes=["ORDER_SEND_RETCODE_NOT_OK"],
        orders_sent=0,
        orders_accepted=0,
        order_send_result={"retcode": 10030, "order": 0, "deal": 0},
    )
    config = TradingConfig(execution=ExecutionConfig(allow_order_send=True, one_shot_only=True))
    client = FakeDemoOrderClient(post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path, config=config)

    assert event["final_decision"] == "SENT"
    assert len(client.order_send_checked_calls) == 1


def test_daily_loss_guard_blocks_when_threshold_exceeded(tmp_path):
    losing_deal = SimpleNamespace(
        symbol="GOLD_",
        magic=26052601,
        profit=-150.0,
        swap=0.0,
        commission=0.0,
        fee=0.0,
        volume=0.0,
    )
    config = TradingConfig(
        execution=ExecutionConfig(allow_order_send=True),
        risk=RiskConfig(max_daily_loss_pct=1.0),
    )
    client = FakeDemoOrderClient(history_deals=[losing_deal], post_send_positions=[matching_position()])

    event = run_demo(client, tmp_path, config=config)

    assert event["final_decision"] == "BLOCK"
    assert REASON_DAILY_LOSS_LIMIT_REACHED in event["reason_codes"]
    assert client.order_send_checked_calls == []


def test_default_config_still_has_allow_order_send_false():
    config = load_trading_config("configs/xm_gold_ai_trader.demo.yaml")

    assert config.execution.allow_order_send is False
