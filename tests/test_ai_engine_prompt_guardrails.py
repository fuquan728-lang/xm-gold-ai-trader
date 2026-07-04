from core.ai_engine import AIAnalyzer


def make_analyzer() -> AIAnalyzer:
    analyzer = AIAnalyzer.__new__(AIAnalyzer)
    analyzer.use_deepseek = True
    analyzer.api_key = "sk-" + "a" * 32
    return analyzer


def test_prompt_uses_gold_pips_and_points() -> None:
    prompt = make_analyzer().build_prompt(
        "GOLD_",
        4031.49,
        4032.01,
        1782820000,
        indicators={"rsi": 61.13, "macd_main": 2.82231, "macd_signal": 2.59469, "ema50": 4021.43},
        include_account_context=False,
    )

    assert "52.0 points = 5.2 pips" in prompt
    assert "RSI(14): 61.1" in prompt
    assert "禁止编造未提供的RSI/MACD/EMA/点差数据" in prompt


def test_prompt_does_not_ask_model_to_randomize_confidence() -> None:
    prompt = make_analyzer().build_prompt(
        "GOLD_",
        4031.49,
        4032.01,
        1782820000,
        indicators={"rsi": 61.13, "macd_main": 2.82231, "macd_signal": 2.59469, "ema50": 4021.43},
        include_account_context=False,
    )

    assert "随机选取" not in prompt
    assert "严禁重复输出相同confidence" not in prompt
    assert "confidence应可复现" in prompt
