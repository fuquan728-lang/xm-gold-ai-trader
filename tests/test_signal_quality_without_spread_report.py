from scripts.signal_quality_without_spread_report import build_signal_quality_without_spread_report


def observation(
    *,
    raw: str,
    final: str = "HOLD",
    confidence: float,
    blocked_by: list[str],
) -> dict:
    return {
        "timestamp": "2026-07-03T10:00:00",
        "request_id": f"REQ_{raw}_{confidence}",
        "symbol": "GOLD_",
        "timeframe": "M5",
        "spread_pips": 5.5,
        "rsi": 52.0,
        "macd_main": 1.0,
        "macd_signal": 0.5,
        "ema50": 4100.0,
        "ai_action_raw": raw,
        "ai_action_final": final,
        "confidence": confidence,
        "blocked_by": blocked_by,
        "response_matched": True,
        "stale_response": False,
        "timeout": False,
        "trade_executed": False,
        "latency_ms": 2500,
    }


def test_spread_only_directional_signal_becomes_counterfactual_candidate():
    report = build_signal_quality_without_spread_report(
        [
            observation(raw="BUY", confidence=0.72, blocked_by=["ACTION_HOLD", "SPREAD_TOO_HIGH"]),
            observation(raw="HOLD", confidence=0.66, blocked_by=["ACTION_HOLD", "SPREAD_TOO_HIGH"]),
        ],
        target=2,
    )

    assert report["status"] == "SIGNAL_CANDIDATES_FOUND"
    assert report["directional_raw_signals"] == 1
    assert report["counterfactual_candidates_without_spread"] == 1
    assert report["candidate_action_counts"] == {"BUY": 1, "SELL": 0, "HOLD": 0}


def test_non_spread_quality_blocks_are_still_kept():
    report = build_signal_quality_without_spread_report(
        [
            observation(
                raw="BUY",
                confidence=0.55,
                blocked_by=["ACTION_HOLD", "SPREAD_TOO_HIGH", "LOW_CONFIDENCE", "INDICATOR_QUALITY_GATE"],
            ),
            observation(
                raw="SELL",
                confidence=0.70,
                blocked_by=["ACTION_HOLD", "SPREAD_TOO_HIGH", "SAFETY_GATE"],
            ),
        ],
        target=2,
    )

    assert report["status"] == "DIRECTIONAL_BUT_LOW_QUALITY"
    assert report["counterfactual_candidates_without_spread"] == 0
    assert report["rejected_directional_reasons"]["LOW_CONFIDENCE"] == 1
    assert report["rejected_directional_reasons"]["INDICATOR_QUALITY_GATE"] == 1
    assert report["rejected_directional_reasons"]["SAFETY_GATE"] == 1
