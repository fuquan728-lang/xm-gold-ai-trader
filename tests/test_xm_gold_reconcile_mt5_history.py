from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.reconcile_demo_journal import JournalEntry
from scripts.reconcile_mt5_history import (
    CLASS_CLOSED_IN_HISTORY,
    CLASS_INVALID_SENT_JOURNAL,
    CLASS_OPEN_POSITION_MATCHED,
    CLASS_SENT_BUT_NOT_FOUND,
    REASON_SENT_BUT_NOT_FOUND,
    REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING,
    reconcile_mt5_history_entries,
)


def sent_payload(**overrides):
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "manual_demo_micro_order",
        "journal_schema_version": 1,
        "timestamp_utc": "2026-05-27T00:00:00+00:00",
        "final_decision": "SENT",
        "reason_codes": [],
        "orders_sent": 1,
        "orders_accepted": 1,
        "account": {"login": 123, "server": "XM demo"},
        "symbol": {"name": "GOLD_"},
        "config": {"symbol": "GOLD_", "magic_number": 26052601},
        "candidate_order": {"symbol": "GOLD_", "mt5_request": {"magic": 26052601}},
        "order_send_result": {"retcode": 10009, "order": 111, "deal": 222},
        "position_verification": {"checked": True, "matched": True},
    }
    payload.update(overrides)
    return payload


def entry(tmp_path, name, payload):
    return JournalEntry(path=tmp_path / name, payload=payload)


class FakeHistoryClient:
    def __init__(self, *, positions=None, orders=None, deals=None) -> None:
        self.positions = positions or []
        self.orders = orders or []
        self.deals = deals or []
        self.open_position_symbols: list[str] = []
        self.history_order_calls = 0
        self.history_deal_calls = 0

    def get_open_positions(self, symbol):
        self.open_position_symbols.append(symbol)
        return self.positions

    def get_history_orders(self, date_from, date_to):
        self.history_order_calls += 1
        return self.orders

    def get_history_deals(self, date_from, date_to):
        self.history_deal_calls += 1
        return self.deals


def reconcile(entries, client):
    return reconcile_mt5_history_entries(
        entries=entries,
        client=client,
        now_utc=datetime(2026, 5, 27, tzinfo=timezone.utc),
    )


def test_sent_journal_open_position_matched(tmp_path):
    client = FakeHistoryClient(positions=[SimpleNamespace(symbol="GOLD_", magic=26052601, ticket=9001)])

    event = reconcile([entry(tmp_path, "sent.json", sent_payload())], client)

    assert event["final_decision"] == "ALLOW"
    assert event["sent_journals_checked"] == 1
    assert event["open_positions_matched"] == 1
    assert event["history_matches"][0]["classification"] == CLASS_OPEN_POSITION_MATCHED


def test_sent_journal_closed_in_mt5_history(tmp_path):
    client = FakeHistoryClient(
        orders=[SimpleNamespace(ticket=111, symbol="GOLD_", magic=26052601)],
        deals=[SimpleNamespace(ticket=222, order=111, symbol="GOLD_", magic=26052601)],
    )

    event = reconcile([entry(tmp_path, "sent.json", sent_payload())], client)

    assert event["final_decision"] == "ALLOW"
    assert event["closed_in_history"] == 1
    assert event["history_matches"][0]["classification"] == CLASS_CLOSED_IN_HISTORY


def test_rejected_order_send_is_not_counted_as_sent(tmp_path):
    rejected = sent_payload(
        final_decision="BLOCK",
        reason_codes=["ORDER_SEND_RETCODE_NOT_OK"],
        orders_accepted=0,
        order_send_result={"retcode": 10030, "order": 0, "deal": 0},
    )
    client = FakeHistoryClient()

    event = reconcile([entry(tmp_path, "rejected.json", rejected)], client)

    assert event["final_decision"] == "ALLOW"
    assert event["sent_journals_checked"] == 0
    assert event["rejected_order_sends"] == 1
    assert client.history_order_calls == 0
    assert client.history_deal_calls == 0


def test_sent_journal_missing_from_positions_and_history_blocks(tmp_path):
    client = FakeHistoryClient()

    event = reconcile([entry(tmp_path, "sent.json", sent_payload())], client)

    assert event["final_decision"] == "BLOCK"
    assert REASON_SENT_BUT_NOT_FOUND in event["reason_codes"]
    assert event["missing_in_history"] == 1
    assert event["history_matches"][0]["classification"] == CLASS_SENT_BUT_NOT_FOUND


def test_candidate_sent_journal_missing_required_fields_blocks(tmp_path):
    invalid = sent_payload(
        candidate_order={},
        symbol={},
        config={},
        order_send_result={"retcode": 10009},
    )

    event = reconcile([entry(tmp_path, "invalid.json", invalid)], client=None)

    assert event["final_decision"] == "BLOCK"
    assert REASON_SENT_JOURNAL_REQUIRED_FIELD_MISSING in event["reason_codes"]
    assert event["sent_journals_checked"] == 1
    assert event["invalid_sent_journals"] == 1
    assert event["history_matches"][0]["classification"] == CLASS_INVALID_SENT_JOURNAL
    assert "candidate_order.symbol_or_symbol.name" in event["history_matches"][0]["missing_fields"]
    assert "config.magic_number" in event["history_matches"][0]["missing_fields"]
    assert "order_send_result.order_or_deal" in event["history_matches"][0]["missing_fields"]
