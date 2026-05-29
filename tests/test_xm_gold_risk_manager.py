from __future__ import annotations

import pytest

from src.strategy.risk_manager import (
    AccountState,
    REASON_BUY_TP_NOT_ABOVE_ENTRY,
    REASON_LOT_BELOW_VOLUME_MIN,
    REASON_MAX_DAILY_LOSS,
    REASON_MAX_SPREAD_EXCEEDED,
    REASON_ONE_POSITION_ONLY,
    REASON_SL_BELOW_BROKER_STOPS_LEVEL,
    REASON_TP_BELOW_BROKER_STOPS_LEVEL,
    RiskConfig,
    RiskManager,
    RiskValidationError,
    TradeRiskRequest,
    calculate_position_size,
)


SYMBOL_INFO_FIXTURE = {
    "name": "GOLD_",
    "point": 0.01,
    "trade_tick_size": 0.01,
    "trade_tick_value": 1.0,
    "volume_min": 0.01,
    "volume_max": 50.0,
    "volume_step": 0.01,
    "trade_stops_level": 0,
}


def test_lot_size_uses_mt5_symbol_info_fields():
    volume = calculate_position_size(
        account_equity=10_000.0,
        risk_per_trade_pct=1.0,
        stop_distance_points=100.0,
        symbol_info=SYMBOL_INFO_FIXTURE,
    )

    assert volume == 1.0


def test_lot_size_floors_to_volume_step():
    volume = calculate_position_size(
        account_equity=10_000.0,
        risk_per_trade_pct=0.25,
        stop_distance_points=333.0,
        symbol_info=SYMBOL_INFO_FIXTURE,
    )

    assert volume == 0.07


def test_lot_size_does_not_round_up_to_minimum_lot():
    volume = calculate_position_size(
        account_equity=100.0,
        risk_per_trade_pct=0.1,
        stop_distance_points=100.0,
        symbol_info=SYMBOL_INFO_FIXTURE,
    )

    assert volume == 0.0


def test_max_daily_loss_blocks_new_trade():
    decision = RiskManager(RiskConfig(max_daily_loss_pct=1.0)).assess_trade(
        TradeRiskRequest(
            symbol_info=SYMBOL_INFO_FIXTURE,
            account=AccountState(balance=10_000.0, equity=10_000.0, daily_realized_pnl=-100.01),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2399.0,
            current_spread_points=50.0,
        )
    )

    assert not decision.allowed
    assert decision.volume == 0.0
    assert REASON_MAX_DAILY_LOSS in decision.reason_codes
    assert any("max daily loss" in reason for reason in decision.reasons)


def test_max_spread_blocks_new_trade():
    decision = RiskManager(RiskConfig(max_spread_points=30.0)).assess_trade(
        TradeRiskRequest(
            symbol_info=SYMBOL_INFO_FIXTURE,
            account=AccountState(balance=10_000.0, equity=10_000.0),
            side="SELL",
            entry_price=2400.0,
            stop_loss_price=2401.0,
            current_spread_points=31.0,
        )
    )

    assert not decision.allowed
    assert REASON_MAX_SPREAD_EXCEEDED in decision.reason_codes
    assert any("spread too wide" in reason for reason in decision.reasons)


def test_one_position_only_blocks_new_trade():
    decision = RiskManager().assess_trade(
        TradeRiskRequest(
            symbol_info=SYMBOL_INFO_FIXTURE,
            account=AccountState(balance=10_000.0, equity=10_000.0),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2399.0,
            current_spread_points=50.0,
            open_positions=(object(),),
        )
    )

    assert not decision.allowed
    assert REASON_ONE_POSITION_ONLY in decision.reason_codes
    assert any("one-position-only" in reason for reason in decision.reasons)


def test_broker_stops_level_blocks_too_close_stop():
    symbol_info = dict(SYMBOL_INFO_FIXTURE)
    symbol_info["trade_stops_level"] = 150
    decision = RiskManager().assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info,
            account=AccountState(balance=10_000.0, equity=10_000.0),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2399.0,
            current_spread_points=50.0,
        )
    )

    assert not decision.allowed
    assert REASON_SL_BELOW_BROKER_STOPS_LEVEL in decision.reason_codes
    assert any("broker stops level" in reason for reason in decision.reasons)


def test_broker_stops_level_blocks_too_close_take_profit():
    symbol_info = dict(SYMBOL_INFO_FIXTURE)
    symbol_info["trade_stops_level"] = 150
    decision = RiskManager().assess_trade(
        TradeRiskRequest(
            symbol_info=symbol_info,
            account=AccountState(balance=10_000.0, equity=10_000.0),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2398.0,
            take_profit_price=2401.0,
            current_spread_points=50.0,
        )
    )

    assert not decision.allowed
    assert REASON_TP_BELOW_BROKER_STOPS_LEVEL in decision.reason_codes
    assert any("take-profit distance" in reason for reason in decision.reasons)


def test_invalid_take_profit_direction_is_blocked():
    decision = RiskManager().assess_trade(
        TradeRiskRequest(
            symbol_info=SYMBOL_INFO_FIXTURE,
            account=AccountState(balance=10_000.0, equity=10_000.0),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2399.0,
            take_profit_price=2399.5,
            current_spread_points=50.0,
        )
    )

    assert not decision.allowed
    assert REASON_BUY_TP_NOT_ABOVE_ENTRY in decision.reason_codes


def test_risk_decision_reason_strings_include_codes_when_blocked():
    decision = RiskManager().assess_trade(
        TradeRiskRequest(
            symbol_info=SYMBOL_INFO_FIXTURE,
            account=AccountState(balance=100.0, equity=100.0),
            side="BUY",
            entry_price=2400.0,
            stop_loss_price=2399.0,
            current_spread_points=50.0,
        )
    )

    assert not decision.allowed
    assert decision.reason_codes == (REASON_LOT_BELOW_VOLUME_MIN,)
    assert decision.reasons[0].startswith(f"{REASON_LOT_BELOW_VOLUME_MIN}:")


def test_prohibited_position_sizing_modes_raise():
    with pytest.raises(RiskValidationError):
        RiskConfig(allow_martingale=True)
    with pytest.raises(RiskValidationError):
        RiskConfig(allow_grid=True)
    with pytest.raises(RiskValidationError):
        RiskConfig(allow_lot_increase_after_loss=True)
