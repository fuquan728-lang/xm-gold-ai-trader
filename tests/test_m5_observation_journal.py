import json

from core.observation_journal import (
    M5ObservationJournal,
    build_observation,
    iter_observations,
    summarize_observations,
)


def sample_request():
    return {
        "request_id": "GOLD__5_1782990278_998156",
        "symbol": "GOLD_",
        "bid": 4066.01,
        "ask": 4066.56,
        "rsi": 46.0,
        "macd_main": 0.1609,
        "macd_signal": 0.5117,
        "ema50": 4065.44,
        "ea_timeout_seconds": 45,
    }


def sample_response():
    return {
        "protocol_version": "v0.25.7",
        "request_id": "GOLD__5_1782990278_998156",
        "action": "HOLD",
        "confidence": 0.60,
        "reason": "test hold",
        "indicator_validation": {
            "original_action": "BUY",
            "spread_pips": 5.5,
        },
        "response_matched": True,
        "stale_response": False,
        "latency_total_ms": 2580,
        "latency_ai_ms": 2400,
        "blocked_by": ["ACTION_HOLD", "SPREAD_TOO_HIGH", "LOW_CONFIDENCE"],
        "use_deepseek": True,
        "cached": False,
    }


def test_build_observation_derives_m5_and_required_fields():
    observation = build_observation(sample_request(), sample_response())

    assert observation["request_id"] == "GOLD__5_1782990278_998156"
    assert observation["timeframe"] == "M5"
    assert observation["symbol"] == "GOLD_"
    assert observation["spread_pips"] == 5.5
    assert observation["ai_action_raw"] == "BUY"
    assert observation["ai_action_final"] == "HOLD"
    assert observation["blocked_by"] == ["ACTION_HOLD", "SPREAD_TOO_HIGH", "LOW_CONFIDENCE"]
    assert observation["response_matched"] is True
    assert observation["stale_response"] is False
    assert observation["latency_ms"] == 2580
    assert observation["trade_executed"] is False


def test_journal_writes_jsonl_and_report_counts(tmp_path):
    journal = M5ObservationJournal(tmp_path)
    path = journal.record(sample_request(), sample_response())

    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mode"] == "m5_formal_observation"

    report = summarize_observations(iter_observations(tmp_path), target=1)

    assert report["total_requests"] == 1
    assert report["matched_responses"] == 1
    assert report["stale_responses_ignored"] == 0
    assert report["timeouts"] == 0
    assert report["ai_action_raw_BUY"] == 1
    assert report["final_action_HOLD"] == 1
    assert report["blocked_by_ACTION_HOLD"] == 1
    assert report["blocked_by_SPREAD_TOO_HIGH"] == 1
    assert report["blocked_by_LOW_CONFIDENCE"] == 1
    assert report["trades_executed"] == 0
    assert report["checkpoint_pass"] is True
