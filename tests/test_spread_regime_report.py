from scripts.spread_regime_report import build_spread_regime_report, iter_historical_spread_observations


def observation(
    *,
    timestamp: str,
    spread_pips: float,
    raw: str = "HOLD",
    final: str = "HOLD",
    confidence: float = 0.65,
    blocked_by: list[str] | None = None,
) -> dict:
    return {
        "timestamp": timestamp,
        "request_id": f"REQ_{timestamp}",
        "symbol": "GOLD_",
        "timeframe": "M5",
        "spread_pips": spread_pips,
        "ai_action_raw": raw,
        "ai_action_final": final,
        "confidence": confidence,
        "blocked_by": blocked_by or ["ACTION_HOLD", "SPREAD_TOO_HIGH"],
        "response_matched": True,
        "stale_response": False,
        "timeout": False,
        "trade_executed": False,
        "latency_ms": 2500,
    }


def test_spread_regime_in_progress_until_target_met():
    rows = [
        observation(timestamp="2026-07-03T09:00:00", spread_pips=5.5),
        observation(timestamp="2026-07-03T09:05:00", spread_pips=5.6),
    ]

    report = build_spread_regime_report(rows, target=3)

    assert report["status"] == "IN_PROGRESS"
    assert report["total_observations"] == 2
    assert report["target_met"] is False
    assert report["journal_quality_pass"] is True


def test_spread_regime_blocks_when_p50_is_above_unsuitable_threshold():
    rows = [
        observation(timestamp="2026-07-03T09:00:00", spread_pips=5.2, raw="BUY"),
        observation(timestamp="2026-07-03T15:00:00", spread_pips=5.5),
        observation(timestamp="2026-07-03T21:00:00", spread_pips=5.8, raw="SELL"),
    ]

    report = build_spread_regime_report(rows, target=3)

    assert report["status"] == "BLOCKED"
    assert report["spread_pips"]["p50"] == 5.5
    assert report["raw_action_counts"] == {"BUY": 1, "SELL": 1, "HOLD": 1}
    assert report["final_action_counts"] == {"BUY": 0, "SELL": 0, "HOLD": 3}
    assert report["raw_buy_to_hold"] == 1
    assert report["raw_sell_to_hold"] == 1
    assert report["spread_buckets"]["5.0-6.0"] == 3


def test_spread_regime_can_identify_session_gate_candidate():
    rows = [
        observation(timestamp="2026-07-03T09:00:00", spread_pips=2.8),
        observation(timestamp="2026-07-03T09:05:00", spread_pips=3.1),
        observation(timestamp="2026-07-03T15:00:00", spread_pips=5.5),
        observation(timestamp="2026-07-03T21:00:00", spread_pips=5.8),
    ]

    report = build_spread_regime_report(rows, target=4)

    asia = next(session for session in report["sessions"] if session["session"] == "asia")
    assert report["status"] == "SESSION_GATE_CANDIDATE"
    assert asia["tradable_candidate"] is True
    assert asia["p50"] == 2.95
    assert asia["p75"] == 3.025


def test_spread_regime_fails_when_quality_gate_fails():
    rows = [
        observation(timestamp="2026-07-03T09:00:00", spread_pips=2.5),
        {
            **observation(timestamp="2026-07-03T09:05:00", spread_pips=2.6),
            "timeout": True,
        },
    ]

    report = build_spread_regime_report(rows, target=2)

    assert report["status"] == "FAIL"
    assert report["timeouts"] == 1
    assert report["journal_quality_pass"] is False


def test_historical_csv_spread_points_are_converted_to_gold_pips(tmp_path):
    csv_path = tmp_path / "gold_m15.csv"
    csv_path.write_text(
        "\n".join(
            [
                "time,open,high,low,close,tick_volume,spread,real_volume",
                "2026-03-10 04:00:00+00:00,5184.17,5186.88,5170.46,5175.19,5465,45,0",
                "2026-03-10 07:00:00+00:00,5175.18,5180.95,5172.38,5179.74,3586,30,0",
            ]
        ),
        encoding="utf-8",
    )

    rows = list(
        iter_historical_spread_observations(
            csv_path,
            symbol="GOLD_",
            timeframe="M15",
            symbol_info={"point": 0.01},
        )
    )
    report = build_spread_regime_report(rows, symbol="GOLD_", timeframe="M15", target=2)

    assert rows[0]["spread_pips"] == 4.5
    assert round(rows[1]["spread_pips"], 4) == 3.0
    assert rows[0]["timestamp"].endswith("+08:00")
    assert report["spread_pips"]["at_or_below_threshold_count"] == 1
    assert report["sessions"][0]["session"] == "new_york"
    assert report["sessions"][1]["session"] == "asia"
    assert report["best_hours_by_p75"][0]["hour"] == 15
