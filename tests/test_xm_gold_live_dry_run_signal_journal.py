from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.dry_run_signal_report import (
    REASON_JOURNAL_JSON_INVALID,
    REASON_JOURNAL_REQUIRED_FIELD_MISSING,
    summarize_dry_run_signals,
)
from scripts.live_dry_run_signal_journal import (
    REASON_SKIP_DUPLICATE_BAR,
    REASON_NO_ACTIONABLE_SIGNAL,
    observe_once,
    run_loop,
)
from src.cli_contract import event_exit_code
from src.runtime.lock import REASON_EMERGENCY_STOP_FILE_PRESENT


def test_live_journal_never_calls_order_send_or_order_check(tmp_path):
    FakeMT5Client.order_check_called = False
    FakeMT5Client.order_send_called = False

    event = observe_once(args(tmp_path), client_factory=FakeMT5Client, journal_dir=tmp_path)

    assert event["orders_sent"] == 0
    assert event["order_check_called"] is False
    assert event["order_send_called"] is False
    assert FakeMT5Client.order_check_called is False
    assert FakeMT5Client.order_send_called is False


def test_once_writes_one_journal(tmp_path):
    event = observe_once(args(tmp_path), client_factory=FakeMT5Client, journal_dir=tmp_path)

    journals = list(tmp_path.glob("*.json"))
    assert len(journals) == 1
    assert event["journal_path"] == str(journals[0])
    assert json.loads(journals[0].read_text(encoding="utf-8"))["orders_sent"] == 0


def test_loop_respects_max_iterations(tmp_path):
    loop_args = args(tmp_path, loop=True, max_iterations=3)
    payload = run_loop(
        loop_args,
        client_factory=FakeMT5Client,
        sleep=lambda _seconds: None,
        journal_dir=tmp_path,
    )

    assert payload["iterations"] == 3
    assert payload["orders_sent"] == 0
    assert len(list(tmp_path.glob("*.json"))) == 3


def test_emergency_stop_is_recorded_without_blocking_observation(tmp_path):
    stop_path = tmp_path / "EMERGENCY_STOP"
    stop_path.write_text("stop", encoding="utf-8")

    event = observe_once(
        args(tmp_path),
        client_factory=FakeMT5Client,
        journal_dir=tmp_path,
        emergency_stop_path=stop_path,
    )

    assert event["orders_sent"] == 0
    assert event["final_decision"] == "BLOCK"
    assert REASON_EMERGENCY_STOP_FILE_PRESENT in event["reason_codes"]
    assert event["account"]["login"] == 68204467
    assert event["symbol"]["name"] == "GOLD_"


def test_same_latest_closed_bar_is_skipped_when_bar_close_only_enabled(tmp_path):
    first = observe_once(
        args(tmp_path, bar_close_only=True, campaign_id="campaign-a"),
        client_factory=FakeMT5Client,
        journal_dir=tmp_path,
    )
    second = observe_once(
        args(tmp_path, bar_close_only=True, campaign_id="campaign-a"),
        client_factory=FakeMT5Client,
        journal_dir=tmp_path,
    )

    assert first["journal_path"]
    assert second["final_decision"] == "SKIP"
    assert second["reason_codes"] == [REASON_SKIP_DUPLICATE_BAR]
    assert second["orders_sent"] == 0
    assert second["order_check_called"] is False
    assert second["order_send_called"] is False
    assert second["journal_path"] is None
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_new_latest_closed_bar_writes_new_journal_when_bar_close_only_enabled(tmp_path):
    ShiftingMT5Client.time_offset_seconds = 0
    first = observe_once(
        args(tmp_path, bar_close_only=True, campaign_id="campaign-b"),
        client_factory=ShiftingMT5Client,
        journal_dir=tmp_path,
    )
    ShiftingMT5Client.time_offset_seconds = 900
    second = observe_once(
        args(tmp_path, bar_close_only=True, campaign_id="campaign-b"),
        client_factory=ShiftingMT5Client,
        journal_dir=tmp_path,
    )

    assert first["journal_path"]
    assert second["journal_path"]
    assert second["latest_closed_bar_time"] > first["latest_closed_bar_time"]
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_skip_duplicate_bar_is_controlled_exit_code_zero(tmp_path):
    observe_once(args(tmp_path, bar_close_only=True), client_factory=FakeMT5Client, journal_dir=tmp_path)
    event = observe_once(args(tmp_path, bar_close_only=True), client_factory=FakeMT5Client, journal_dir=tmp_path)

    assert event["final_decision"] == "SKIP"
    assert event_exit_code(event) == 0


def test_report_summarizes_reason_codes(tmp_path):
    write_json(
        tmp_path / "block.json",
        journal(
            final_decision="BLOCK",
            reason_codes=[REASON_NO_ACTIONABLE_SIGNAL, REASON_EMERGENCY_STOP_FILE_PRESENT],
            spread=55.0,
        ),
    )
    write_json(tmp_path / "signal.json", journal(final_decision="SIGNAL", reason_codes=[], spread=25.0))

    report = summarize_dry_run_signals(tmp_path)

    assert report["total_observations"] == 2
    assert report["signal_count"] == 1
    assert report["block_count"] == 1
    assert report["reason_code_counts"][REASON_NO_ACTIONABLE_SIGNAL] == 1
    assert report["emergency_stop_seen_count"] == 1
    assert report["avg_spread"] == 40.0
    assert report["max_spread"] == 55.0
    assert report["orders_sent"] == 0


def test_missing_and_malformed_journals_are_handled_safely(tmp_path):
    (tmp_path / "bad.json").write_text("{not-json", encoding="utf-8")
    write_json(tmp_path / "missing.json", {"project": "xm-gold-ai-trader"})

    report = summarize_dry_run_signals(tmp_path)

    assert report["malformed_journals"] == 1
    assert report["missing_required_field_journals"] == 1
    assert report["reason_code_counts"][REASON_JOURNAL_JSON_INVALID] == 1
    assert report["reason_code_counts"][REASON_JOURNAL_REQUIRED_FIELD_MISSING] == 1
    assert report["orders_sent"] == 0


class FakeMT5Client:
    order_check_called = False
    order_send_called = False

    def __init__(self, _config) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False

    def ensure_symbol(self, symbol):
        assert symbol == "GOLD_"

    def get_account_info(self):
        raw = {
            "login": 68204467,
            "server": "XMGlobal-MT5 2",
            "trade_mode": 0,
            "trade_allowed": True,
            "trade_expert": True,
            "balance": 10_000.0,
            "equity": 10_000.0,
            "currency": "USD",
        }
        return SimpleNamespace(raw=raw)

    def get_symbol_info(self, symbol):
        assert symbol == "GOLD_"
        raw = {
            "name": "GOLD_",
            "description": "GOLD_",
            "path": "Derivatives\\SpotMetals_\\GOLD_",
            "point": 0.01,
            "digits": 2,
            "spread": 20,
            "trade_tick_size": 0.01,
            "trade_tick_value": 1.0,
            "trade_contract_size": 100.0,
            "volume_min": 0.01,
            "volume_max": 50.0,
            "volume_step": 0.01,
            "trade_stops_level": 0,
            "trade_mode": 4,
        }
        return SimpleNamespace(raw=raw, point=0.01)

    def get_symbol_tick(self, symbol):
        assert symbol == "GOLD_"
        raw = {"bid": 4500.00, "ask": 4500.20, "last": 0.0, "time": 1779800000}
        return SimpleNamespace(raw=raw, bid=4500.00, ask=4500.20)

    def copy_rates_from_pos(self, symbol, timeframe, count, start_pos=1):
        assert symbol == "GOLD_"
        assert timeframe == "M15"
        assert start_pos == 1
        return make_rates(count)

    def get_open_positions(self, symbol):
        assert symbol == "GOLD_"
        return []

    def get_daily_realized_pnl(self, symbol):
        assert symbol == "GOLD_"
        return 0.0

    def order_check(self, _request):
        FakeMT5Client.order_check_called = True
        raise AssertionError("order_check must never be called by live dry-run journal")

    def order_send(self, _request):
        FakeMT5Client.order_send_called = True
        raise AssertionError("order_send must never be called by live dry-run journal")


class ShiftingMT5Client(FakeMT5Client):
    time_offset_seconds = 0

    def copy_rates_from_pos(self, symbol, timeframe, count, start_pos=1):
        rates = make_rates(count)
        for row in rates:
            row["time"] += self.time_offset_seconds
        return rates


def args(tmp_path, *, loop=False, max_iterations=None, campaign_id=None, bar_close_only=False):
    return SimpleNamespace(
        config="configs/xm_gold_ai_trader.demo.yaml",
        symbol="GOLD_",
        timeframe="M15",
        bars=60,
        start_pos=1,
        parameter_report=str(tmp_path / "missing_parameter_report.json"),
        journal_dir=str(tmp_path),
        campaign_id=campaign_id,
        fallback_fast_sma=2,
        fallback_slow_sma=3,
        atr_period=2,
        fallback_atr_stop_multiplier=1.5,
        fallback_reward_risk_ratio=1.5,
        once=not loop,
        loop=loop,
        interval_seconds=0.0,
        max_iterations=max_iterations,
        bar_close_only=bar_close_only,
        terminal_path=None,
        login=None,
        password=None,
        server=None,
        timeout_ms=60_000,
        json=True,
    )


def make_rates(count: int):
    rates = []
    for index in range(count):
        close = 100.0 + (index % 3) * 0.01
        rates.append(
            {
                "time": 1_700_000_000 + (index * 900),
                "open": close,
                "high": close + 0.10,
                "low": close - 0.10,
                "close": close,
                "spread": 20.0,
            }
        )
    return rates


def journal(*, final_decision: str, reason_codes: list[str], spread: float):
    return {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "timestamp_utc": "2026-05-27T00:00:00+00:00",
        "final_decision": final_decision,
        "reason_codes": reason_codes,
        "reasons": [],
        "orders_sent": 0,
        "current_spread_points": spread,
        "risk_preview": {"reason_codes": reason_codes},
    }


def write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
