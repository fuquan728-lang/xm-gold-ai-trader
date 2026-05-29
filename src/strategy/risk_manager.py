from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from typing import Any, Mapping, Sequence


class RiskValidationError(ValueError):
    """Raised when risk inputs are missing or unsafe."""


REASON_UNSUPPORTED_SIDE = "UNSUPPORTED_SIDE"
REASON_INVALID_ACCOUNT = "INVALID_ACCOUNT"
REASON_MAX_DAILY_LOSS = "MAX_DAILY_LOSS"
REASON_MAX_SPREAD_EXCEEDED = "MAX_SPREAD_EXCEEDED"
REASON_ONE_POSITION_ONLY = "ONE_POSITION_ONLY"
REASON_STOP_DISTANCE_TOO_SMALL = "STOP_DISTANCE_TOO_SMALL"
REASON_SL_BELOW_BROKER_STOPS_LEVEL = "SL_BELOW_BROKER_STOPS_LEVEL"
REASON_TP_BELOW_BROKER_STOPS_LEVEL = "TP_BELOW_BROKER_STOPS_LEVEL"
REASON_BUY_SL_NOT_BELOW_ENTRY = "BUY_SL_NOT_BELOW_ENTRY"
REASON_SELL_SL_NOT_ABOVE_ENTRY = "SELL_SL_NOT_ABOVE_ENTRY"
REASON_BUY_TP_NOT_ABOVE_ENTRY = "BUY_TP_NOT_ABOVE_ENTRY"
REASON_SELL_TP_NOT_BELOW_ENTRY = "SELL_TP_NOT_BELOW_ENTRY"
REASON_LOT_BELOW_VOLUME_MIN = "LOT_BELOW_VOLUME_MIN"


@dataclass(frozen=True, slots=True)
class SymbolSpec:
    """Trading contract details read from MetaTrader5.symbol_info()."""

    name: str
    point: float
    trade_tick_size: float
    trade_tick_value: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_stops_level: int = 0
    spread: int | None = None

    @classmethod
    def from_mt5(cls, symbol_info: Any) -> "SymbolSpec":
        """Create a symbol spec from an MT5 symbol_info object or mapping."""

        return cls(
            name=str(_read_field(symbol_info, "name")),
            point=_positive_float(symbol_info, "point"),
            trade_tick_size=_positive_float(symbol_info, "trade_tick_size"),
            trade_tick_value=_positive_float(symbol_info, "trade_tick_value"),
            volume_min=_positive_float(symbol_info, "volume_min"),
            volume_max=_positive_float(symbol_info, "volume_max"),
            volume_step=_positive_float(symbol_info, "volume_step"),
            trade_stops_level=int(_read_optional_field(symbol_info, "trade_stops_level", 0) or 0),
            spread=_optional_int(symbol_info, "spread"),
        )

    def validate(self) -> None:
        if self.volume_min > self.volume_max:
            raise RiskValidationError("symbol volume_min is greater than volume_max")


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_spread_points: float = 350.0
    one_position_only: bool = True
    max_lot_per_trade: float | None = None
    min_stop_distance_points: float = 1.0
    allow_martingale: bool = False
    allow_grid: bool = False
    allow_lot_increase_after_loss: bool = False

    def __post_init__(self) -> None:
        if self.risk_per_trade_pct <= 0:
            raise RiskValidationError("risk_per_trade_pct must be positive")
        if self.risk_per_trade_pct > 5:
            raise RiskValidationError("risk_per_trade_pct must be <= 5 for this safety-first system")
        if self.max_daily_loss_pct <= 0:
            raise RiskValidationError("max_daily_loss_pct must be positive")
        if self.max_spread_points <= 0:
            raise RiskValidationError("max_spread_points must be positive")
        if self.min_stop_distance_points <= 0:
            raise RiskValidationError("min_stop_distance_points must be positive")
        if self.max_lot_per_trade is not None and self.max_lot_per_trade <= 0:
            raise RiskValidationError("max_lot_per_trade must be positive when set")
        if self.allow_martingale:
            raise RiskValidationError("martingale is explicitly prohibited")
        if self.allow_grid:
            raise RiskValidationError("grid trading is explicitly prohibited")
        if self.allow_lot_increase_after_loss:
            raise RiskValidationError("automatic lot increase after loss is explicitly prohibited")


@dataclass(frozen=True, slots=True)
class AccountState:
    balance: float
    equity: float
    daily_realized_pnl: float = 0.0
    trading_day: date | None = None


@dataclass(frozen=True, slots=True)
class TradeRiskRequest:
    symbol_info: Any
    account: AccountState
    side: str
    entry_price: float
    stop_loss_price: float
    current_spread_points: float
    take_profit_price: float | None = None
    open_positions: Sequence[Any] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RiskDecision:
    allowed: bool
    volume: float
    reason_codes: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    risk_amount: float = 0.0
    risk_per_lot: float = 0.0
    stop_distance_points: float = 0.0
    take_profit_distance_points: float | None = None


class RiskManager:
    """Central risk gate for the first production version."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def assess_trade(self, request: TradeRiskRequest) -> RiskDecision:
        spec = SymbolSpec.from_mt5(request.symbol_info)
        spec.validate()

        reasons: list[str] = []
        reason_codes: list[str] = []
        side = request.side.upper()
        if side not in {"BUY", "SELL"}:
            _block(reason_codes, reasons, REASON_UNSUPPORTED_SIDE, f"unsupported side: {request.side}")

        if request.account.equity <= 0 or request.account.balance <= 0:
            _block(reason_codes, reasons, REASON_INVALID_ACCOUNT, "account balance/equity must be positive")

        daily_loss_limit = (
            max_daily_loss_amount(request.account.balance, self.config.max_daily_loss_pct)
            if request.account.balance > 0
            else 0.0
        )
        if daily_loss_limit and request.account.daily_realized_pnl <= -daily_loss_limit:
            _block(
                reason_codes,
                reasons,
                REASON_MAX_DAILY_LOSS,
                "max daily loss reached: "
                f"{request.account.daily_realized_pnl:.2f} <= -{daily_loss_limit:.2f}",
            )

        if request.current_spread_points > self.config.max_spread_points:
            _block(
                reason_codes,
                reasons,
                REASON_MAX_SPREAD_EXCEEDED,
                f"spread too wide: {request.current_spread_points:.1f} > "
                f"{self.config.max_spread_points:.1f} points",
            )

        if self.config.one_position_only and len(request.open_positions) > 0:
            _block(
                reason_codes,
                reasons,
                REASON_ONE_POSITION_ONLY,
                "one-position-only protection: existing position is open",
            )

        stop_distance_points = abs(request.entry_price - request.stop_loss_price) / spec.point
        take_profit_distance_points = (
            abs(request.take_profit_price - request.entry_price) / spec.point
            if request.take_profit_price is not None
            else None
        )
        if stop_distance_points < self.config.min_stop_distance_points:
            _block(
                reason_codes,
                reasons,
                REASON_STOP_DISTANCE_TOO_SMALL,
                f"stop distance too small: {stop_distance_points:.1f} < "
                f"{self.config.min_stop_distance_points:.1f} points",
            )
        if spec.trade_stops_level and stop_distance_points < spec.trade_stops_level:
            _block(
                reason_codes,
                reasons,
                REASON_SL_BELOW_BROKER_STOPS_LEVEL,
                f"stop distance below broker stops level: "
                f"{stop_distance_points:.1f} < {spec.trade_stops_level} points",
            )
        if (
            spec.trade_stops_level
            and take_profit_distance_points is not None
            and take_profit_distance_points < spec.trade_stops_level
        ):
            _block(
                reason_codes,
                reasons,
                REASON_TP_BELOW_BROKER_STOPS_LEVEL,
                f"take-profit distance below broker stops level: "
                f"{take_profit_distance_points:.1f} < {spec.trade_stops_level} points",
            )
        if side == "BUY" and request.stop_loss_price >= request.entry_price:
            _block(reason_codes, reasons, REASON_BUY_SL_NOT_BELOW_ENTRY, "BUY stop loss must be below entry")
        if side == "SELL" and request.stop_loss_price <= request.entry_price:
            _block(reason_codes, reasons, REASON_SELL_SL_NOT_ABOVE_ENTRY, "SELL stop loss must be above entry")
        if request.take_profit_price is not None:
            if side == "BUY" and request.take_profit_price <= request.entry_price:
                _block(
                    reason_codes,
                    reasons,
                    REASON_BUY_TP_NOT_ABOVE_ENTRY,
                    "BUY take profit must be above entry",
                )
            if side == "SELL" and request.take_profit_price >= request.entry_price:
                _block(
                    reason_codes,
                    reasons,
                    REASON_SELL_TP_NOT_BELOW_ENTRY,
                    "SELL take profit must be below entry",
                )

        risk_amount = (
            trade_risk_amount(request.account.equity, self.config.risk_per_trade_pct)
            if request.account.equity > 0
            else 0.0
        )
        risk_per_lot = risk_per_lot_for_stop(spec, stop_distance_points) if stop_distance_points > 0 else 0.0
        volume = 0.0
        if not reasons:
            volume = calculate_position_size(
                account_equity=request.account.equity,
                risk_per_trade_pct=self.config.risk_per_trade_pct,
                stop_distance_points=stop_distance_points,
                symbol_info=spec,
                max_lot_per_trade=self.config.max_lot_per_trade,
            )
            if volume <= 0:
                _block(
                    reason_codes,
                    reasons,
                    REASON_LOT_BELOW_VOLUME_MIN,
                    "risk budget is too small for broker minimum volume",
                )

        return RiskDecision(
            allowed=not reasons,
            volume=volume if not reasons else 0.0,
            reason_codes=tuple(reason_codes),
            reasons=tuple(reasons),
            risk_amount=risk_amount,
            risk_per_lot=risk_per_lot,
            stop_distance_points=stop_distance_points,
            take_profit_distance_points=take_profit_distance_points,
        )


def calculate_position_size(
    *,
    account_equity: float,
    risk_per_trade_pct: float,
    stop_distance_points: float,
    symbol_info: Any,
    max_lot_per_trade: float | None = None,
) -> float:
    """Calculate a risk-based lot size without hardcoded GOLD_ contract specs."""

    if account_equity <= 0:
        raise RiskValidationError("account_equity must be positive")
    if risk_per_trade_pct <= 0:
        raise RiskValidationError("risk_per_trade_pct must be positive")
    if stop_distance_points <= 0:
        raise RiskValidationError("stop_distance_points must be positive")

    spec = symbol_info if isinstance(symbol_info, SymbolSpec) else SymbolSpec.from_mt5(symbol_info)
    spec.validate()
    risk_amount = trade_risk_amount(account_equity, risk_per_trade_pct)
    risk_per_lot = risk_per_lot_for_stop(spec, stop_distance_points)
    raw_volume = risk_amount / risk_per_lot
    if max_lot_per_trade is not None:
        raw_volume = min(raw_volume, max_lot_per_trade)
    return floor_volume_to_step(raw_volume, spec.volume_min, spec.volume_max, spec.volume_step)


def trade_risk_amount(account_equity: float, risk_per_trade_pct: float) -> float:
    if account_equity <= 0:
        raise RiskValidationError("account_equity must be positive")
    if risk_per_trade_pct <= 0:
        raise RiskValidationError("risk_per_trade_pct must be positive")
    return account_equity * (risk_per_trade_pct / 100.0)


def max_daily_loss_amount(account_balance: float, max_daily_loss_pct: float) -> float:
    if account_balance <= 0:
        raise RiskValidationError("account_balance must be positive")
    if max_daily_loss_pct <= 0:
        raise RiskValidationError("max_daily_loss_pct must be positive")
    return account_balance * (max_daily_loss_pct / 100.0)


def risk_per_lot_for_stop(symbol_info: Any, stop_distance_points: float) -> float:
    spec = symbol_info if isinstance(symbol_info, SymbolSpec) else SymbolSpec.from_mt5(symbol_info)
    spec.validate()
    if stop_distance_points <= 0:
        raise RiskValidationError("stop_distance_points must be positive")

    price_distance = stop_distance_points * spec.point
    ticks = price_distance / spec.trade_tick_size
    risk_per_lot = ticks * spec.trade_tick_value
    if risk_per_lot <= 0:
        raise RiskValidationError("risk_per_lot must be positive")
    return risk_per_lot


def floor_volume_to_step(volume: float, volume_min: float, volume_max: float, volume_step: float) -> float:
    """Floor volume to broker step; return 0 if minimum lot would exceed risk budget."""

    if volume <= 0:
        return 0.0
    for value, name in (
        (volume_min, "volume_min"),
        (volume_max, "volume_max"),
        (volume_step, "volume_step"),
    ):
        if value <= 0:
            raise RiskValidationError(f"{name} must be positive")
    if volume_min > volume_max:
        raise RiskValidationError("volume_min is greater than volume_max")

    capped = min(volume, volume_max)
    step = _decimal(volume_step)
    floored = (_decimal(capped) / step).to_integral_value(rounding=ROUND_FLOOR) * step
    if floored < _decimal(volume_min):
        return 0.0
    return float(floored.normalize())


def spread_points_from_prices(bid: float, ask: float, point: float) -> float:
    if bid <= 0 or ask <= 0 or point <= 0:
        raise RiskValidationError("bid, ask, and point must be positive")
    if ask < bid:
        raise RiskValidationError("ask must be greater than or equal to bid")
    return (ask - bid) / point


def _read_field(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        if name not in source:
            raise RiskValidationError(f"symbol_info is missing {name}")
        return source[name]
    if not hasattr(source, name):
        raise RiskValidationError(f"symbol_info is missing {name}")
    return getattr(source, name)


def _read_optional_field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _positive_float(source: Any, name: str) -> float:
    value = float(_read_field(source, name))
    if value <= 0:
        raise RiskValidationError(f"symbol_info.{name} must be positive")
    return value


def _optional_int(source: Any, name: str) -> int | None:
    value = _read_optional_field(source, name)
    return None if value is None else int(value)


def _decimal(value: float) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise RiskValidationError(f"invalid decimal value: {value}") from exc


def _block(codes: list[str], reasons: list[str], code: str, reason: str) -> None:
    codes.append(code)
    reasons.append(f"{code}: {reason}")
