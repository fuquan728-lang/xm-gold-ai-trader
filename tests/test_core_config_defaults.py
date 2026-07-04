from core import config as config_module


def test_min_confidence_default_matches_safe_mode(monkeypatch):
    monkeypatch.delenv("MIN_CONFIDENCE", raising=False)
    monkeypatch.setattr(config_module.dotenv, "load_dotenv", lambda *args, **kwargs: None)

    cfg = config_module.Config()

    assert cfg.MIN_CONFIDENCE == 0.65
