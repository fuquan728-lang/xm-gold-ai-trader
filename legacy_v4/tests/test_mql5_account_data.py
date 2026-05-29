from core.mql5_data import MQL5DataManager


def test_zero_margin_level_without_used_margin_is_normalized_safe():
    manager = MQL5DataManager()

    manager.update_from_json(
        {
            "type": "mql5_data",
            "account": {
                "balance": 10000.0,
                "equity": 10000.0,
                "margin": 0.0,
                "margin_free": 10000.0,
                "margin_level": 0.0,
                "profit": 0.0,
            },
            "positions": [],
        }
    )

    assert manager.account_info.margin_level == 1000.0
