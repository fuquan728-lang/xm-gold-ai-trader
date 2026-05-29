from __future__ import annotations

import json
from types import SimpleNamespace

from scripts.dry_run_campaign_report import (
    REASON_JOURNAL_MISSING_CAMPAIGN_ID,
    summarize_campaigns,
)
from scripts.dry_run_signal_report import REASON_JOURNAL_JSON_INVALID
from scripts.run_dry_observation_campaign import run_campaign
from src.runtime.lock import REASON_EMERGENCY_STOP_FILE_PRESENT
from tests.test_xm_gold_live_dry_run_signal_journal import FakeMT5Client


def test_campaign_stops_at_max_iterations(tmp_path):
    metadata = run_campaign(campaign_args(tmp_path, max_iterations=3), client_factory=FakeMT5Client, sleep=no_sleep)

    assert metadata["total_iterations"] == 3
    assert metadata["total_poll_iterations"] == 3
    assert metadata["journal_count"] == 3
    assert metadata["orders_sent"] == 0
    assert len(list((tmp_path / "journals").glob("*.json"))) == 3


def test_campaign_writes_metadata(tmp_path):
    metadata = run_campaign(campaign_args(tmp_path, campaign_id="campaign-test-1"), client_factory=FakeMT5Client, sleep=no_sleep)

    path = tmp_path / "campaigns" / "campaign-test-1.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["campaign_id"] == "campaign-test-1"
    assert payload["started_at_utc"]
    assert payload["ended_at_utc"]
    assert payload["orders_sent"] == 0
    assert metadata["campaign_path"] == str(path)


def test_every_observation_has_orders_sent_zero(tmp_path):
    metadata = run_campaign(campaign_args(tmp_path, max_iterations=2), client_factory=FakeMT5Client, sleep=no_sleep)

    assert metadata["observed_orders_sent_sum"] == 0
    for path in metadata["journal_paths"]:
        payload = json.loads(open(path, encoding="utf-8").read())
        assert payload["campaign_id"] == metadata["campaign_id"]
        assert payload["orders_sent"] == 0
        assert payload["order_check_called"] is False
        assert payload["order_send_called"] is False


def test_campaign_report_counts_skipped_duplicate_bars(tmp_path):
    metadata = run_campaign(
        campaign_args(tmp_path, max_iterations=3, campaign_id="bar-close-campaign", bar_close_only=True),
        client_factory=FakeMT5Client,
        sleep=no_sleep,
    )
    report = summarize_campaigns(campaign_dir=tmp_path / "campaigns", journal_dir=tmp_path / "journals")

    assert metadata["total_poll_iterations"] == 3
    assert metadata["journal_count"] == 1
    assert metadata["unique_closed_bars"] == 1
    assert metadata["duplicate_bar_skipped"] == 2
    assert report["total_observations"] == 3
    assert report["unique_closed_bars"] == 1
    assert report["duplicate_skip_count"] == 2
    assert report["reason_code_counts"]["SKIP_DUPLICATE_BAR"] == 2
    assert report["orders_sent"] == 0


def test_campaign_report_handles_missing_and_malformed_journals(tmp_path):
    campaign_dir = tmp_path / "campaigns"
    journal_dir = tmp_path / "journals"
    campaign_dir.mkdir()
    journal_dir.mkdir()
    write_json(
        campaign_dir / "campaign-a.json",
        {
            "project": "xm-gold-ai-trader",
            "mode": "dry_observation_campaign",
            "campaign_id": "campaign-a",
            "orders_sent": 0,
            "total_iterations": 1,
            "journal_count": 1,
        },
    )
    write_json(journal_dir / "unlinked.json", journal(campaign_id=None, final_decision="BLOCK"))
    (journal_dir / "malformed.json").write_text("{bad", encoding="utf-8")

    report = summarize_campaigns(campaign_dir=campaign_dir, journal_dir=journal_dir)

    assert report["orders_sent"] == 0
    assert report["malformed_journals"] == 1
    assert report["unlinked_observation_count"] == 1
    assert report["reason_code_counts"][REASON_JOURNAL_JSON_INVALID] == 1
    assert report["reason_code_counts"][REASON_JOURNAL_MISSING_CAMPAIGN_ID] == 1


def test_emergency_stop_is_recorded_but_does_not_send_orders(tmp_path):
    stop_path = tmp_path / "EMERGENCY_STOP"
    stop_path.write_text("stop", encoding="utf-8")

    metadata = run_campaign(
        campaign_args(tmp_path, max_iterations=1),
        client_factory=FakeMT5Client,
        sleep=no_sleep,
        emergency_stop_path=stop_path,
    )

    payload = json.loads(open(metadata["journal_paths"][0], encoding="utf-8").read())
    assert payload["orders_sent"] == 0
    assert payload["final_decision"] == "BLOCK"
    assert REASON_EMERGENCY_STOP_FILE_PRESENT in payload["reason_codes"]


def campaign_args(tmp_path, *, max_iterations=1, campaign_id=None, bar_close_only=False):
    return SimpleNamespace(
        config="configs/xm_gold_ai_trader.demo.yaml",
        symbol="GOLD_",
        timeframe="M15",
        interval_seconds=0.0,
        max_iterations=max_iterations,
        campaign_id=campaign_id,
        campaign_dir=str(tmp_path / "campaigns"),
        journal_dir=str(tmp_path / "journals"),
        bar_close_only=bar_close_only,
        bars=60,
        start_pos=1,
        parameter_report=str(tmp_path / "missing_parameter_report.json"),
        fallback_fast_sma=2,
        fallback_slow_sma=3,
        atr_period=2,
        fallback_atr_stop_multiplier=1.5,
        fallback_reward_risk_ratio=1.5,
        terminal_path=None,
        login=None,
        password=None,
        server=None,
        timeout_ms=60_000,
        json=True,
    )


def journal(*, campaign_id, final_decision):
    return {
        "journal_schema_version": 1,
        "project": "xm-gold-ai-trader",
        "mode": "live_dry_run_signal_journal",
        "campaign_id": campaign_id,
        "timestamp_utc": "2026-05-27T08:00:00+00:00",
        "final_decision": final_decision,
        "reason_codes": ["NO_ACTIONABLE_SIGNAL"],
        "reasons": [],
        "orders_sent": 0,
        "current_spread_points": 50.0,
    }


def write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def no_sleep(_seconds: float) -> None:
    return None
