from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.demo_lifecycle_report import list_open_matching_positions, summarize_demo_lifecycle
from scripts.reconcile_demo_journal import (
    REASON_LEGACY_JOURNAL_SCHEMA,
    REASON_UNKNOWN_JOURNAL_SCHEMA,
    REASON_JOURNAL_ACCOUNT_SUMMARY_MISSING,
    REASON_JOURNAL_JSON_INVALID,
    REASON_JOURNAL_NOT_OBJECT,
    REASON_JOURNAL_ORDER_SEND_RESULT_MISSING,
    REASON_JOURNAL_POSITION_VERIFICATION_MISSING,
    REASON_JOURNAL_SYMBOL_MISMATCH,
    load_journal_entries,
    reconcile_demo_journal,
)
from src.broker.order_executor import TradingConfig


def valid_journal(**overrides):
    payload = {
        "project": "xm-gold-ai-trader",
        "mode": "manual_demo_micro_order",
        "journal_schema_version": 1,
        "timestamp_utc": "2026-05-27T00:00:00+00:00",
        "block_stage": "post_order_send",
        "side": "BUY",
        "final_decision": "SENT",
        "reason_codes": [],
        "reasons": [],
        "orders_sent": 1,
        "config": {"symbol": "GOLD_", "magic_number": 26052601},
        "account": {"login": 123, "server": "XM demo"},
        "symbol": {"name": "GOLD_"},
        "candidate_order": {"symbol": "GOLD_", "mt5_request": {"magic": 26052601}},
        "local_risk_decision": {"allowed": True},
        "order_check_result": {"retcode": 0},
        "order_send_result": {"retcode": 10009},
        "position_verification": {"checked": True, "matched": True, "matching_positions": []},
    }
    payload.update(overrides)
    return payload


def write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_schema_v1_valid_blocked_journal_passes(tmp_path):
    write_json(
        tmp_path / "blocked.json",
        valid_journal(
            final_decision="BLOCK",
            block_stage="post_mt5",
            reason_codes=["ALLOW_ORDER_SEND_FALSE"],
            orders_sent=0,
            order_send_result=None,
            position_verification=None,
        ),
    )

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "ALLOW"
    assert event["findings"] == []


def test_v1_confirmation_missing_pre_confirmation_journal_passes_audit(tmp_path):
    write_json(
        tmp_path / "pre_confirmation.json",
        valid_journal(
            final_decision="BLOCK",
            block_stage="pre_confirmation",
            side="SELL",
            reason_codes=["DEMO_ORDER_CONFIRMATION_MISSING"],
            orders_sent=0,
            account=None,
            symbol=None,
            tick=None,
            candidate_order=None,
            local_risk_decision=None,
            order_check_result=None,
            order_send_result=None,
            position_verification=None,
        ),
    )

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "ALLOW"
    assert event["findings"] == []


def test_pre_confirmation_side_is_preserved_in_journal_payload(tmp_path):
    payload = valid_journal(
        final_decision="BLOCK",
        block_stage="pre_confirmation",
        side="SELL",
        reason_codes=["DEMO_ORDER_CONFIRMATION_MISSING"],
        orders_sent=0,
        account=None,
        symbol=None,
        candidate_order=None,
        local_risk_decision=None,
        order_check_result=None,
        order_send_result=None,
        position_verification=None,
    )
    write_json(tmp_path / "pre_confirmation.json", payload)

    entries = load_journal_entries(tmp_path)

    assert entries[0].payload["side"] == "SELL"


def test_schema_v1_valid_sent_journal_passes(tmp_path):
    write_json(tmp_path / "ok.json", valid_journal())

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "ALLOW"
    assert event["findings"] == []


def test_reconcile_handles_malformed_json(tmp_path):
    (tmp_path / "bad.json").write_text("{bad json", encoding="utf-8")

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_JSON_INVALID in event["reason_codes"]


def test_reconcile_handles_non_object_json(tmp_path):
    write_json(tmp_path / "array.json", [])

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_NOT_OBJECT in event["reason_codes"]


def test_schema_v1_sent_journal_missing_order_send_result_fails(tmp_path):
    write_json(tmp_path / "missing_send.json", valid_journal(order_send_result=None))

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_ORDER_SEND_RESULT_MISSING in event["reason_codes"]


def test_sent_journal_missing_account_server_fails(tmp_path):
    write_json(tmp_path / "missing_account.json", valid_journal(account={"login": 123}))

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_ACCOUNT_SUMMARY_MISSING in event["reason_codes"]


def test_sent_journal_missing_position_verification_fails(tmp_path):
    write_json(tmp_path / "missing_position.json", valid_journal(position_verification=None))

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_POSITION_VERIFICATION_MISSING in event["reason_codes"]


def test_reconcile_flags_missing_required_fields(tmp_path):
    malformed = valid_journal(
        orders_sent=1,
        account={},
        symbol={"name": "XAUEUR_"},
        candidate_order={"symbol": "XAUEUR_", "mt5_request": {"magic": 26052601}},
        order_send_result=None,
        position_verification=None,
    )
    write_json(tmp_path / "missing.json", malformed)

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_JOURNAL_SYMBOL_MISMATCH in event["reason_codes"]
    assert REASON_JOURNAL_ORDER_SEND_RESULT_MISSING in event["reason_codes"]
    assert REASON_JOURNAL_POSITION_VERIFICATION_MISSING in event["reason_codes"]
    assert REASON_JOURNAL_ACCOUNT_SUMMARY_MISSING in event["reason_codes"]


def test_legacy_blocked_journal_returns_warning(tmp_path):
    legacy = {
        "project": "xm-gold-ai-trader",
        "mode": "manual_demo_micro_order",
        "final_decision": "BLOCK",
        "reason_codes": ["DEMO_ORDER_CONFIRMATION_MISSING"],
        "orders_sent": 0,
    }
    write_json(tmp_path / "legacy_block.json", legacy)

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "ALLOW"
    assert event["reason_codes"] == []
    assert REASON_LEGACY_JOURNAL_SCHEMA in event["warning_codes"]
    assert event["warning_journals"] == 1


def test_unknown_schema_fails_with_explicit_code(tmp_path):
    write_json(tmp_path / "unknown.json", valid_journal(journal_schema_version=999))

    event = reconcile_demo_journal(journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert event["final_decision"] == "BLOCK"
    assert REASON_UNKNOWN_JOURNAL_SCHEMA in event["reason_codes"]


def test_lifecycle_report_counts_sent_blocked_and_reason_codes(tmp_path):
    write_json(tmp_path / "sent.json", valid_journal())
    write_json(
        tmp_path / "blocked.json",
        valid_journal(
            final_decision="BLOCK",
            orders_sent=0,
            block_stage="pre_confirmation",
            side="BUY",
            reason_codes=["DEMO_ORDER_CONFIRMATION_MISSING"],
            account=None,
            symbol=None,
            candidate_order=None,
            local_risk_decision=None,
            order_check_result=None,
            order_send_result=None,
            position_verification=None,
        ),
    )
    entries = load_journal_entries(tmp_path)

    report = summarize_demo_lifecycle(entries=entries, journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert report["sent_orders"] == 1
    assert report["blocked_attempts"] == 1
    assert report["reason_code_counts"] == {"DEMO_ORDER_CONFIRMATION_MISSING": 1}
    assert report["pre_confirmation_blocks"] == 1
    assert report["valid_journals"] == 2
    assert report["legacy_journals"] == 0
    assert report["malformed_journals"] == 0
    assert report["failed_audit_journals"] == 0
    assert report["warning_journals"] == 0


def test_lifecycle_report_final_decision_sent_alone_does_not_count_as_sent(tmp_path):
    write_json(
        tmp_path / "sent_label_only.json",
        valid_journal(
            final_decision="SENT",
            orders_sent=0,
            orders_accepted=0,
            order_send_result=None,
            position_verification=None,
        ),
    )
    entries = load_journal_entries(tmp_path)

    report = summarize_demo_lifecycle(entries=entries, journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert report["sent_orders"] == 0
    assert report["order_send_attempts"] == 0


def test_lifecycle_report_successful_retcode_with_order_counts_as_sent(tmp_path):
    write_json(
        tmp_path / "accepted.json",
        valid_journal(
            final_decision="BLOCK",
            orders_sent=0,
            orders_accepted=0,
            reason_codes=["POSITION_VERIFICATION_FAILED"],
            order_send_result={"retcode": 10009, "order": 111, "deal": 222},
        ),
    )
    entries = load_journal_entries(tmp_path)

    report = summarize_demo_lifecycle(entries=entries, journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert report["sent_orders"] == 1
    assert report["order_send_attempts"] == 1
    assert report["rejected_order_sends"] == 0


def test_lifecycle_report_failed_retcode_counts_as_rejected_send(tmp_path):
    write_json(
        tmp_path / "rejected.json",
        valid_journal(
            final_decision="BLOCK",
            orders_sent=0,
            orders_accepted=0,
            reason_codes=["ORDER_SEND_RETCODE_NOT_OK"],
            order_send_result={"retcode": 10030, "order": 0, "deal": 0},
        ),
    )
    entries = load_journal_entries(tmp_path)

    report = summarize_demo_lifecycle(entries=entries, journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert report["sent_orders"] == 0
    assert report["order_send_attempts"] == 1
    assert report["rejected_order_sends"] == 1


def test_lifecycle_report_order_send_attempts_count_accepted_and_rejected(tmp_path):
    write_json(
        tmp_path / "accepted.json",
        valid_journal(
            final_decision="BLOCK",
            orders_sent=0,
            orders_accepted=0,
            reason_codes=["POSITION_VERIFICATION_FAILED"],
            order_send_result={"retcode": 10009, "order": 111, "deal": 222},
        ),
    )
    write_json(
        tmp_path / "rejected.json",
        valid_journal(
            final_decision="BLOCK",
            orders_sent=0,
            orders_accepted=0,
            reason_codes=["ORDER_SEND_RETCODE_NOT_OK"],
            order_send_result={"retcode": 10030, "order": 0, "deal": 0},
        ),
    )
    entries = load_journal_entries(tmp_path)

    report = summarize_demo_lifecycle(entries=entries, journal_dir=tmp_path, expected_symbol="GOLD_", project_magic=26052601)

    assert report["order_send_attempts"] == 2
    assert report["sent_orders"] == 1
    assert report["rejected_order_sends"] == 1


def test_lifecycle_report_lists_only_matching_open_positions():
    config = TradingConfig()
    matching = SimpleNamespace(symbol="GOLD_", magic=26052601, ticket=1)
    wrong_magic = SimpleNamespace(symbol="GOLD_", magic=111, ticket=2)
    wrong_symbol = SimpleNamespace(symbol="XAUEUR_", magic=26052601, ticket=3)
    client = SimpleNamespace(get_open_positions=lambda symbol: [matching, wrong_magic, wrong_symbol])

    positions = list_open_matching_positions(client, config)

    assert len(positions) == 1
    assert positions[0]["ticket"] == 1
