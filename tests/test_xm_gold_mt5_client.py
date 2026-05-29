from __future__ import annotations

from types import SimpleNamespace

from src.broker import mt5_client


def test_select_order_filling_uses_numeric_symbol_flags_when_python_constants_are_missing(monkeypatch):
    fake_mt5 = SimpleNamespace(
        ORDER_FILLING_FOK=0,
        ORDER_FILLING_IOC=1,
        ORDER_FILLING_RETURN=2,
        ORDER_FILLING_BOC=3,
    )
    monkeypatch.setattr(mt5_client, "mt5", fake_mt5)

    assert mt5_client.select_order_filling(1) == 0
    assert mt5_client.select_order_filling(2) == 1
    assert mt5_client.select_order_filling(4) == 3
