from core.ai_engine import AIAnalyzer


def make_analyzer(api_key: str, use_deepseek: bool = True) -> AIAnalyzer:
    analyzer = AIAnalyzer.__new__(AIAnalyzer)
    analyzer.api_key = api_key
    analyzer.use_deepseek = use_deepseek
    return analyzer


def test_placeholder_deepseek_key_is_not_valid() -> None:
    analyzer = make_analyzer("YOUR_DEEPSEEK_API_KEY_HERE")

    assert not analyzer.has_valid_api_key()
    assert not analyzer.is_deepseek_available()


def test_deepseek_key_must_look_like_secret_key() -> None:
    analyzer = make_analyzer("not-a-secret")

    assert not analyzer.has_valid_api_key()


def test_realistic_deepseek_key_shape_is_available_when_enabled() -> None:
    analyzer = make_analyzer("sk-" + "a" * 32)

    assert analyzer.has_valid_api_key()
    assert analyzer.is_deepseek_available()
