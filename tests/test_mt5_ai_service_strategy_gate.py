from core.validator import IndicatorAnalyzer
from mt5_ai_service import MT5AITradingService, build_indicator_fingerprint
import mt5_ai_service
from core.service.ai_coordinator import AIServiceCoordinator
import core.service.ai_coordinator as ai_coordinator_module


class MemoryCache:
    def __init__(self, cached=None):
        self.cached = cached
        self.set_items = []

    def get(self, key):
        return self.cached

    def set(self, key, value):
        self.set_items.append((key, value))


class BuyAnalyzer:
    use_deepseek = True

    def is_deepseek_available(self):
        return True

    def build_prompt(self, *args, **kwargs):
        return "prompt"

    def call_api(self, prompt):
        return {
            "action": "BUY",
            "confidence": 0.91,
            "reason": "AI看多",
            "stop_loss_pips": 40,
            "take_profit_pips": 80,
        }


class HoldAnalyzer(BuyAnalyzer):
    def call_api(self, prompt):
        return {"action": "HOLD", "confidence": 0.62, "reason": "重新分析HOLD"}


def make_service(analyzer):
    service = MT5AITradingService.__new__(MT5AITradingService)
    service.ai_analyzer = analyzer
    service.indicator_analyzer = IndicatorAnalyzer()
    service.risk_manager = None
    service.coordinator = AIServiceCoordinator(analyzer, None, IndicatorAnalyzer())
    return service


def test_service_downgrades_ai_buy_when_gold_spread_is_too_wide(monkeypatch) -> None:
    monkeypatch.setattr(mt5_ai_service.config, "MAX_TRADE_SPREAD_PIPS", 3.0, raising=False)
    monkeypatch.setattr(mt5_ai_service.config, "MIN_INDICATOR_SIGNALS", 3, raising=False)
    monkeypatch.setattr(mt5_ai_service.config, "ALLOW_FALLBACK_TRADING", False, raising=False)
    monkeypatch.setattr(ai_coordinator_module, "global_cache", MemoryCache())

    service = make_service(BuyAnalyzer())
    result = service.analyze(
        "GOLD_",
        4031.49,
        4032.01,
        1782820000,
        indicators={"rsi": 32.0, "macd_main": 1.2, "macd_signal": 0.4, "ema50": 4021.43},
    )

    assert result["action"] == "HOLD"
    assert result["indicator_validation"]["original_action"] == "BUY"
    assert "点差5.2pips>3.0pips" in result["reason"]
    assert "stop_loss_pips" not in result
    assert "take_profit_pips" not in result


def test_service_skips_cached_signal_when_indicator_fingerprint_changes(monkeypatch) -> None:
    current_indicators = {"rsi": 32.0, "macd_main": 1.2, "macd_signal": 0.4, "ema50": 4021.43}
    stale_cached_signal = {
        "action": "BUY",
        "confidence": 0.91,
        "reason": "旧缓存BUY",
        "indicator_fingerprint": build_indicator_fingerprint(
            {"rsi": 70.0, "macd_main": -1.0, "macd_signal": 0.0, "ema50": 4040.0}
        ),
    }
    cache = MemoryCache(stale_cached_signal)
    monkeypatch.setattr(ai_coordinator_module, "global_cache", cache)
    monkeypatch.setattr(mt5_ai_service.config, "ALLOW_FALLBACK_TRADING", False, raising=False)

    service = make_service(HoldAnalyzer())
    result = service.analyze("GOLD_", 4031.49, 4031.59, 1782820000, indicators=current_indicators)

    assert result["action"] == "HOLD"
    assert result["reason"].startswith("重新分析HOLD")
    assert cache.set_items


def test_safe_mode_does_not_reuse_cached_trade_signal(monkeypatch) -> None:
    current_indicators = {"rsi": 32.0, "macd_main": 1.2, "macd_signal": 0.4, "ema50": 4021.43}
    cached_signal = {
        "action": "BUY",
        "confidence": 0.91,
        "reason": "cached BUY",
        "indicator_fingerprint": build_indicator_fingerprint(current_indicators),
        "stop_loss_pips": 40,
        "take_profit_pips": 80,
    }
    cache = MemoryCache(cached_signal)
    monkeypatch.setattr(ai_coordinator_module, "global_cache", cache)
    monkeypatch.setattr(mt5_ai_service.config, "ALLOW_FALLBACK_TRADING", False, raising=False)

    service = make_service(HoldAnalyzer())
    result = service.analyze("GOLD_", 4031.49, 4031.59, 1782820000, indicators=current_indicators)

    assert result["action"] == "HOLD"
    assert "cached BUY" not in result["reason"]
    assert "stop_loss_pips" not in result
    assert "take_profit_pips" not in result
    assert cache.set_items
