from core.ai_engine import AIAnalyzer


def make_analyzer(api_key, use_deepseek=True):
    analyzer = object.__new__(AIAnalyzer)
    analyzer.api_key = api_key
    analyzer.use_deepseek = use_deepseek
    return analyzer


def test_placeholder_deepseek_key_is_not_available():
    analyzer = make_analyzer("your-deepseek-api-key-here")

    assert not analyzer.has_valid_api_key()
    assert not analyzer.is_deepseek_available()
    assert analyzer.get_deepseek_status() == "密钥未设置"


def test_disabled_deepseek_is_not_available_even_with_key():
    analyzer = make_analyzer("sk-valid-looking-key", use_deepseek=False)

    assert analyzer.has_valid_api_key()
    assert not analyzer.is_deepseek_available()
    assert analyzer.get_deepseek_status() == "禁用"


def test_enabled_deepseek_with_key_is_available():
    analyzer = make_analyzer("sk-valid-looking-key", use_deepseek=True)

    assert analyzer.has_valid_api_key()
    assert analyzer.is_deepseek_available()
    assert analyzer.get_deepseek_status() == "启用"
