from core import config
from core.validator import IndicatorAnalyzer


def test_gold_spread_uses_real_pip_size() -> None:
    metrics = IndicatorAnalyzer.spread_metrics("GOLD_", 4031.49, 4032.01)

    assert round(metrics["spread_points"], 1) == 52.0
    assert round(metrics["spread_pips"], 1) == 5.2


def test_actionable_signal_without_indicators_is_downgraded(monkeypatch) -> None:
    monkeypatch.setattr(config, "MIN_INDICATOR_SIGNALS", 3, raising=False)

    result = IndicatorAnalyzer.evaluate_signal(
        "BUY",
        0.88,
        None,
        "GOLD_",
        4031.49,
        4032.01,
    )

    assert result["action"] == "HOLD"
    assert result["adjusted"] is True
    assert "缺少技术指标" in result["reason"]


def test_high_gold_spread_blocks_actionable_signal(monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_TRADE_SPREAD_PIPS", 3.0, raising=False)
    monkeypatch.setattr(config, "MIN_INDICATOR_SIGNALS", 3, raising=False)

    result = IndicatorAnalyzer.evaluate_signal(
        "BUY",
        0.91,
        {"rsi": 32.0, "macd_main": 1.2, "macd_signal": 0.4, "ema50": 4021.43},
        "GOLD_",
        4031.49,
        4032.01,
    )

    assert result["action"] == "HOLD"
    assert result["adjusted"] is True
    assert "点差5.2pips>3.0pips" in result["reason"]


def test_strong_buy_with_acceptable_spread_survives_gate(monkeypatch) -> None:
    monkeypatch.setattr(config, "MAX_TRADE_SPREAD_PIPS", 3.0, raising=False)
    monkeypatch.setattr(config, "MIN_INDICATOR_SIGNALS", 3, raising=False)
    monkeypatch.setattr(config, "MIN_CONSISTENCY", 0.65, raising=False)

    result = IndicatorAnalyzer.evaluate_signal(
        "BUY",
        0.82,
        {"rsi": 32.0, "macd_main": 1.2, "macd_signal": 0.4, "ema50": 4021.43},
        "GOLD_",
        4031.49,
        4031.59,
    )

    assert result["action"] == "BUY"
    assert result["confidence"] == 0.82
    assert result["bullish_signals"] >= 3.0
