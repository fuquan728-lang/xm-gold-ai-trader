from types import SimpleNamespace

from core.cache import global_cache
from mt5_ai_service import MT5AITradingService


def make_assessment(warnings=None, position_size=0.01, risk_reward_ratio=1.5):
    return SimpleNamespace(
        warning_messages=warnings or [],
        recommended_position_size=position_size,
        risk_reward_ratio=risk_reward_ratio,
    )


def test_blocks_margin_insufficient_warning():
    assessment = make_assessment(
        warnings=["[紧急] 保证金不足，无法开仓: 水平0.0%"],
        risk_reward_ratio=0.0,
    )

    reason = MT5AITradingService._get_blocking_risk_reason(assessment)

    assert "保证金不足" in reason


def test_blocks_zero_position_size():
    assessment = make_assessment(position_size=0.0)

    reason = MT5AITradingService._get_blocking_risk_reason(assessment)

    assert reason == "推荐仓位为0，禁止开仓"


def test_blocks_zero_risk_reward_ratio():
    assessment = make_assessment(risk_reward_ratio=0.0)

    reason = MT5AITradingService._get_blocking_risk_reason(assessment)

    assert "风险回报比0.00无效" in reason


def test_allows_non_blocking_medium_risk_warning():
    assessment = make_assessment(
        warnings=["[WARN]  中等风险：建议调整止损或减少仓位"],
        risk_reward_ratio=1.2,
    )

    assert MT5AITradingService._get_blocking_risk_reason(assessment) is None


def test_analyze_downgrades_buy_to_hold_on_margin_block():
    global_cache.clear()
    service = object.__new__(MT5AITradingService)
    service.ai_analyzer = SimpleNamespace(
        use_deepseek=False,
        api_key="",
        is_deepseek_available=lambda: False,
        get_fallback_strategy=lambda *args, **kwargs: (
            "BUY",
            0.85,
            "智能后备: 看涨信号占优",
        ),
    )
    service.risk_manager = SimpleNamespace(
        risk_params=SimpleNamespace(risk_level=SimpleNamespace(value="medium")),
        assess_trade_risk=lambda **kwargs: make_assessment(
            warnings=["[紧急] 保证金不足，无法开仓: 水平0.0%"],
            risk_reward_ratio=0.0,
        ),
    )

    result = service.analyze(
        symbol="GOLD_TEST",
        bid=4562.28,
        ask=4562.86,
        current_time=1779687123,
        indicators={},
    )

    assert result["action"] == "HOLD"
    assert result["confidence"] == 0.0
    assert result["original_action"] == "BUY"
    assert "风险拦截" in result["reason"]
    assert "stop_loss_pips" not in result
    assert "take_profit_pips" not in result
