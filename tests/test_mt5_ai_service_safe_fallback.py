from mt5_ai_service import MT5AITradingService
import mt5_ai_service
from core.service.ai_coordinator import AIServiceCoordinator
import core.service.ai_coordinator as ai_coordinator_module


class NoCache:
    def get(self, key):
        return None


class UnavailableAnalyzer:
    use_deepseek = False

    def is_deepseek_available(self):
        return False

    def get_fallback_strategy(self, *args, **kwargs):
        raise AssertionError("fallback trading must not be used by default")


def test_deepseek_unavailable_defaults_to_hold(monkeypatch) -> None:
    monkeypatch.setattr(mt5_ai_service.config, "ALLOW_FALLBACK_TRADING", False, raising=False)
    monkeypatch.setattr(ai_coordinator_module, "global_cache", NoCache())

    service = MT5AITradingService.__new__(MT5AITradingService)
    analyzer = UnavailableAnalyzer()
    service.ai_analyzer = analyzer
    service.coordinator = AIServiceCoordinator(analyzer, None, None)

    result = service.analyze("GOLD_", 4000.0, 4000.5, 1782820000)

    assert result["action"] == "HOLD"
    assert result["use_deepseek"] is False
    assert "后备交易未启用" in result["reason"]
